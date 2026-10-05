`ifndef MA_AXIS_TYPEDEF_SVH
`define MA_AXIS_TYPEDEF_SVH

`define MA_AXIS_RESP(__name) \
typedef struct packed {         \
   logic tready;               \
  } __name``_axis_resp_t;

`define MA_AXIS_REQ(__name, __type) \
typedef struct packed {         \
   logic tvalid;               \
    __type payload; \
  } __name``_axis_req_t;

`define MA_AXIS_PAYLOAD(__name, __tdata_t) \
typedef struct packed {         \
   logic tlast;               \
    __tdata_t tdata; \
  } __name``_axis_payload_t;
`define MA_AXIS_ALL(__name, __type) \
`MA_AXIS_RESP(__name) \
`MA_AXIS_PAYLOAD(__name, __type) \
`MA_AXIS_REQ(__name, __name``_axis_payload_t) 

`endif  // MA_AXIS_TYPEDEF_SVH
