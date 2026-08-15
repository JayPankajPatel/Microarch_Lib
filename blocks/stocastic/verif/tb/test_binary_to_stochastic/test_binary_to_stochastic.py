# test_my_design.py (simple)
from difflib import restore
import random
import cocotb
from cocotb.triggers import ClockCycles, RisingEdge
from ma_clkrst import reset_dut, start_clock


#interface
# module binary_to_stochastic #(
#     parameter int WIDTH = 4
# ) (
#     input logic clk,
#     input logic [WIDTH-1:0] binary_in,
#     input logic rst_n,
#     output logic stochastic_out
# );
@cocotb.test()
async def smoke_test(dut):
    period_ns = 10 
    max_value = (1 << len(dut.binary_in)) -1 
    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)
    random_binary_in = random.randint(0, max_value)
    dut.binary_in.value = random_binary_in
    await ClockCycles(dut.clk, 100)

