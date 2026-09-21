// Minimal PIO-style programmable sequencer BEL.
//
// ISA (8-bit instructions, [opcode:3][operand:5]):
//   000 SET   pin,val   -- operand[0] = value to drive on `tx`
//   001 OUT              -- shift one bit from the internal tx_data shift register onto `tx`
//   010 WAIT              -- stall until the internal divider's baud tick
//   011 SET_X  n          -- operand[3:0] = literal loaded into loop counter X
//   100 JMP_XDEC addr     -- decrement X; if X was nonzero before the decrement, jump to
//                            operand[3:0], else fall through
//   111 HALT               -- stop; `busy` deasserts, waits for next `start`
//
// Program memory lives in real config bits (ConfigBits), not a parameter -- the whole
// point is that it is reprogrammable post-fabrication by loading a new bitstream, same
// as every other configurable element in the fabric. 9 instructions x 8 bits = 72 bits,
// proven first as a plain-parameter behavioral model (pio_seq.v, scratchpad) before being
// wired here as real config-bit-driven hardware.
//
// Divider and shift-register datapath are embedded directly (not separate BELs) so their
// wiring to the sequencer is internal RTL, not switch-matrix routing -- avoids paying a
// second tile's fixed switch-matrix/config-mem overhead for what is really one primitive.
//
// `div` is config-bit-driven (DIV_0..DIV_7), not a switch-matrix input, same mechanism as
// PROG -- it's a quasi-static baud-rate setting, not something user logic needs to drive
// live cycle-to-cycle, and pulling it off the switch matrix frees 8 of the 32 BEL-input
// slots the switch-matrix generator caps a tile at (needed for packing >1 instance/tile).
// Consequence: changing it at runtime now goes through the same config-frame-write path as
// reprogramming PROG (Fabric/ConfigFSM.v's address-targeted live frame writer), not through
// ordinary routing -- see wiki decision log for the tradeoff.
//
// Restructured to the Gaisler two-process (`r`/`rin`) style per this repo's house
// convention (docs/adr/0007) -- more than a couple of pieces of interacting registered
// state (pc, x, waiting, pin_out, running, shift_step, div_cnt, shreg), originally a
// single always block with several individually-declared registers conditionally
// assigned across nested branches, exactly the shape ADR-0007 found two real FSM bugs
// in for a different module. See blocks/pio_seq/verif/tb/test_pio_seq_prim for the
// isolated (no fabric/switch-matrix/bitstream in the loop) test this restructuring was
// verified against.

`include "ma_assert.svh"

(* FABulous, BelMap,
    PROG_0=0,   PROG_1=1,   PROG_2=2,   PROG_3=3,   PROG_4=4,   PROG_5=5,   PROG_6=6,   PROG_7=7,
    PROG_8=8,   PROG_9=9,   PROG_10=10, PROG_11=11, PROG_12=12, PROG_13=13, PROG_14=14, PROG_15=15,
    PROG_16=16, PROG_17=17, PROG_18=18, PROG_19=19, PROG_20=20, PROG_21=21, PROG_22=22, PROG_23=23,
    PROG_24=24, PROG_25=25, PROG_26=26, PROG_27=27, PROG_28=28, PROG_29=29, PROG_30=30, PROG_31=31,
    PROG_32=32, PROG_33=33, PROG_34=34, PROG_35=35, PROG_36=36, PROG_37=37, PROG_38=38, PROG_39=39,
    PROG_40=40, PROG_41=41, PROG_42=42, PROG_43=43, PROG_44=44, PROG_45=45, PROG_46=46, PROG_47=47,
    PROG_48=48, PROG_49=49, PROG_50=50, PROG_51=51, PROG_52=52, PROG_53=53, PROG_54=54, PROG_55=55,
    PROG_56=56, PROG_57=57, PROG_58=58, PROG_59=59, PROG_60=60, PROG_61=61, PROG_62=62, PROG_63=63,
    PROG_64=64, PROG_65=65, PROG_66=66, PROG_67=67, PROG_68=68, PROG_69=69, PROG_70=70, PROG_71=71,
    DIV_0=72,   DIV_1=73,   DIV_2=74,   DIV_3=75,   DIV_4=76,   DIV_5=77,   DIV_6=78,   DIV_7=79
*)
module pio_seq_prim #(
    parameter int NoConfigBits = 80
) (
    input  logic       rst_n,
    input  logic       start,      // pulse: load tx_data and begin executing from instr 0
    input  logic [7:0] tx_data,    // byte to transmit (parallel load -- cheap, inputs have slack)
    output logic       tx,         // serial output
    output logic       busy,       // 1 while a program is running
    (* CARRY = "dummy" *) input logic dummy_carry_in,
    (* CARRY = "dummy" *) output logic dummy_carry_out,
    (* FABulous, EXTERNAL, SHARED_PORT *) input logic UserCLK,
    (* FABulous, GLOBAL *) input logic [NoConfigBits-1:0] ConfigBits
);
  `MA_ASSERT_ELABOR(PioSeqPrimConfigBitsWidth, NoConfigBits == 80)

  assign dummy_carry_out = dummy_carry_in;

  wire [7:0] div = ConfigBits[79:72];

  function automatic logic [7:0] fetch(logic [3:0] addr);
    fetch = ConfigBits[addr*8+:8];
  endfunction

  localparam logic [2:0] OpSet = 3'b000;
  localparam logic [2:0] OpOut = 3'b001;
  localparam logic [2:0] OpWait = 3'b010;
  localparam logic [2:0] OpSetX = 3'b011;
  localparam logic [2:0] OpJmpXdec = 3'b100;
  localparam logic [2:0] OpHalt = 3'b111;

  typedef struct packed {
    logic [7:0] div_cnt;
    logic [7:0] shreg;
    logic [3:0] pc;
    logic [3:0] x;
    logic       waiting;
    logic       pin_out;
    logic       running;
    logic       shift_step;  // pulses for one cycle to shift shreg the cycle after an OUT
  } state_t;

  state_t r, rin;

  // Divider is free-running (ticks every `div`+1 cycles regardless of sequencer
  // state), same behavior as the original pio_divider.v -- not gated by running/waiting.
  wire baud_tick = (r.div_cnt == 8'd0);

  wire [7:0] instr = fetch(r.pc);
  wire [2:0] opcode = instr[7:5];
  // operand[4] is reserved by the ISA's [opcode:3][operand:5] format for a
  // future opcode that needs a 5-bit field (every current opcode only needs
  // operand[3:0] -- addr fields match pc's 4-bit width, SET only reads bit 0).
  /* verilator lint_off UNUSEDSIGNAL */
  wire [4:0] operand = instr[4:0];
  /* verilator lint_on UNUSEDSIGNAL */

  always_comb begin
    rin = r;  // default: hold every field unless overridden below

    rin.div_cnt = baud_tick ? div : (r.div_cnt - 8'd1);

    if (start) rin.shreg = tx_data;
    else if (r.shift_step) rin.shreg = {1'b0, r.shreg[7:1]};

    rin.shift_step = 1'b0;  // only OP_OUT below re-asserts it, for one cycle

    if (!r.running) begin
      rin.pin_out = 1'b1;
      if (start) begin
        rin.running = 1'b1;
        rin.pc = 4'd0;
        rin.waiting = 1'b0;
      end
    end else if (r.waiting) begin
      if (baud_tick) rin.waiting = 1'b0;
    end else begin
      case (opcode)
        OpSet: begin
          rin.pin_out = operand[0];
          rin.pc = r.pc + 4'd1;
        end
        OpOut: begin
          rin.pin_out = r.shreg[0];
          rin.shift_step = 1'b1;
          rin.pc = r.pc + 4'd1;
        end
        OpWait: begin
          rin.waiting = 1'b1;
          rin.pc = r.pc + 4'd1;
        end
        OpSetX: begin
          rin.x = operand[3:0];
          rin.pc = r.pc + 4'd1;
        end
        OpJmpXdec: begin
          if (r.x != 4'd0) begin
            rin.x = r.x - 4'd1;
            rin.pc = operand[3:0];
          end else begin
            rin.pc = r.pc + 4'd1;
          end
        end
        OpHalt: rin.running = 1'b0;
        default: rin.running = 1'b0;
      endcase
    end
  end

  always_ff @(posedge UserCLK) begin
    if (!rst_n) begin
      r.div_cnt <= 8'd0;
      r.shreg <= 8'd0;
      r.pc <= 4'd0;
      r.x <= 4'd0;
      r.waiting <= 1'b0;
      r.pin_out <= 1'b1;
      r.running <= 1'b0;
      r.shift_step <= 1'b0;
    end else begin
      r <= rin;
    end
  end

  assign tx = r.pin_out;
  assign busy = r.running;
endmodule
