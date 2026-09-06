// Test-only integration wrapper: chains binary_stochastic_converter's
// stochastic_out directly into stochastic_to_binary's stochastic_in, so the
// two converters' independently-verified module-level behavior can be
// exercised together as one system (see docs/adr and GitHub issue #2 for
// why this composition needs its own test -- each module's own testbench
// only agrees with itself on what "one window" means, not with the other
// module). Not a synthesizable product block, so it lives with the test
// rather than under rtl/.
module loopback_top #(
    parameter int WIDTH = 4
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] binary_in,
    input  logic             valid_binary_in,
    input  logic             ready_binary_out,
    output logic             ready_binary_in,
    output logic             valid_binary_out,
    output logic [WIDTH-1:0] binary_out
);
  logic stochastic_link;
  logic valid_stochastic_link;
  logic ready_stochastic_link;
  logic boundary_link;

  binary_stochastic_converter #(
      .WIDTH(WIDTH)
  ) u_encoder (
      .clk(clk),
      .rst_n(rst_n),
      .binary_in(binary_in),
      .valid_binary_in(valid_binary_in),
      .ready_stochastic_out(ready_stochastic_link),
      .ready_binary_in(ready_binary_in),
      .valid_stochastic_out(valid_stochastic_link),
      .stochastic_out(stochastic_link),
      // Wired to the decoder's boundary_in (see docs/adr/0017): this
      // real producer-side "last bit of the burst" event is what keeps
      // the decoder's window aligned to the encoder's burst by
      // construction, instead of by a coincidentally-matching length.
      .last_cycle(boundary_link)
  );

  stochastic_to_binary #(
      .WIDTH(WIDTH)
  ) u_decoder (
      .clk(clk),
      .rst_n(rst_n),
      .stochastic_in(stochastic_link),
      .valid_stochastic_in(valid_stochastic_link),
      .boundary_in(boundary_link),
      .ready_binary_out(ready_binary_out),
      .ready_stochastic_in(ready_stochastic_link),
      .valid_binary_out(valid_binary_out),
      .binary_out(binary_out)
  );
endmodule : loopback_top
