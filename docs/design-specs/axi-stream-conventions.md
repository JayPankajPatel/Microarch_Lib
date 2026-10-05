# AXI-Stream Conventions for Microarch_Lib

How blocks in this library use AXI-Stream, with each rule traced to the spec.
Reference: **Arm IHI 0051B**, *AMBA AXI-Stream Protocol Specification* (2021).
Local copy: `~/Documents/DigitalDesignDocs/AXI-Stream.pdf`.

Legend: **SPEC** is a requirement from IHI 0051B. **CHOICE** is a decision made for this library.

## Stream type

- **SPEC (§1.2.2):** A *continuous aligned stream* is one where "every packet has
  no position bytes or null bytes."
- **CHOICE:** Streams in this library are continuous aligned streams unless a
  block's MAS says otherwise. Audio samples, for example, are all data bytes.

## TKEEP / TSTRB

- **SPEC (§3.1.2, default value rules):**
  - If TKEEP is absent, TKEEP defaults to all bits HIGH.
  - If TSTRB is absent, TSTRB = TKEEP.
  - If both are absent, both default to all bits HIGH.
- **CHOICE:** For continuous aligned streams, `keep`/`strb` are **omitted** from
  the payload struct. The spec defaults give exactly the all-ones behavior these
  streams need, so hand-tied `'1` fields add nothing.

## TLAST

- **SPEC (§3.1.3):** For streams with no packet concept, TLAST may be held LOW
  (one endless packet: best for merging/upsizing, can delay transfers), held HIGH
  (every transfer is its own packet: no interconnect delay, but prevents merging
  and efficient upsizing), or pulsed every N transfers (a compromise).
- **CHOICE:** Each block states its TLAST policy in its MAS. Default for
  low-latency sample streams is **HIGH**. A stereo stream would pulse TLAST every
  2 transfers (end of each L/R frame).

## Byte and item ordering

- **SPEC (§2.4.1, byte locations):** "The low order bytes of the data bus are the
  earlier bytes in a data stream." For a fully packed stream with bus width
  `w` bytes, byte `n` is in transfer `t = INT(n / w)` at byte position
  `b = n - t*w`, i.e. `TDATA[8b+7 : 8b]`.
- **CHOICE:** When several items share one transfer, the **earlier item goes in
  the lower bits**. Example: stereo L/R packed in a 32-bit transfer puts L in
  `TDATA[15:0]` and R in `TDATA[31:16]`.
- **CHOICE:** No RTL implements the byte-location formula yet. Current streams
  carry one item per transfer, so the formula is trivial. Implement it (as a
  utility-package function usable from RTL and TB) when the first width
  converter or packing block needs it. Testbench and golden-model packing must
  follow the same ordering.

## Handshake

- **SPEC (§2.2):** "A Transmitter is not permitted to wait until TREADY is
  asserted before asserting TVALID. Once TVALID is asserted, it must remain
  asserted until the handshake occurs."
- **SPEC (§2.2):** "A Receiver is permitted to wait for TVALID to be asserted
  before asserting TREADY."
- **SPEC (§2.2):** Data and control from the Transmitter must remain unchanged
  once TVALID is asserted, until the handshake.
- **CHOICE:** Every block reacts to a transfer using exactly `valid && ready`,
  with no extra conditions. Conditions for accepting data go into `ready`, never
  into the transfer check.
- **Note:** The "no combinatorial paths between input and output signals" rule
  comes from the full AXI spec (IHI 0022). It is **not** in IHI 0051B. Registering
  `ready` (e.g. with a skid buffer) is therefore a timing/robustness choice for
  streams, not a spec requirement.

## See also

- `common/rtl/ma_axis_typedef.svh`: struct typedef macro (in progress)
- ADRs: struct req/resp ports instead of SV interfaces (to be written)
