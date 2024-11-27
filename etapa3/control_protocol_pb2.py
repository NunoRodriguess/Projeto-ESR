# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: control_protocol.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x16\x63ontrol_protocol.proto\x12\x04node\"\xec\x02\n\x0e\x43ontrolMessage\x12.\n\x04type\x18\x01 \x01(\x0e\x32 .node.ControlMessage.MessageType\x12\x0f\n\x07node_ip\x18\x02 \x01(\t\x12\x0f\n\x07node_id\x18\x03 \x01(\t\x12\x11\n\tnode_type\x18\x04 \x01(\t\x12%\n\tneighbors\x18\x05 \x03(\x0b\x32\x12.node.NeighborInfo\x12\x14\n\x0c\x63ontrol_port\x18\x06 \x01(\x05\x12\x11\n\tdata_port\x18\x07 \x01(\x05\x12\x11\n\ttimestamp\x18\x08 \x01(\x02\x12\x18\n\x10\x61\x63\x63umulated_time\x18\t \x01(\x02\x12\x11\n\trtsp_port\x18\n \x01(\x05\"e\n\x0bMessageType\x12\x0c\n\x08REGISTER\x10\x00\x12\x15\n\x11REGISTER_RESPONSE\x10\x01\x12\x08\n\x04PING\x10\x02\x12\x08\n\x04PONG\x10\x03\x12\x14\n\x10UPDATE_NEIGHBORS\x10\x04\x12\x07\n\x03\x41\x43K\x10\x05\"\x7f\n\x0cNeighborInfo\x12\x0f\n\x07node_id\x18\x01 \x01(\t\x12\x0f\n\x07node_ip\x18\x02 \x01(\t\x12\x11\n\tnode_type\x18\x03 \x01(\t\x12\x14\n\x0c\x63ontrol_port\x18\x04 \x01(\x05\x12\x11\n\tdata_port\x18\x05 \x01(\x05\x12\x11\n\trtsp_port\x18\x06 \x01(\x05\"\xaa\x02\n\x0f\x46loodingMessage\x12/\n\x04type\x18\x01 \x01(\x0e\x32!.node.FloodingMessage.MessageType\x12\x11\n\tsource_id\x18\x02 \x01(\t\x12\x12\n\nstream_ids\x18\x03 \x03(\t\x12\x11\n\tsource_ip\x18\x04 \x01(\t\x12\x13\n\x0broute_state\x18\x05 \x01(\t\x12\x0e\n\x06metric\x18\x06 \x01(\x05\x12\x14\n\x0c\x63ontrol_port\x18\x07 \x01(\x05\x12\x11\n\trtsp_port\x18\x08 \x01(\x05\x12\x10\n\x08rtp_port\x18\t \x01(\x05\"L\n\x0bMessageType\x12\x13\n\x0f\x46LOODING_UPDATE\x10\x00\x12\x12\n\x0e\x41\x43TIVATE_ROUTE\x10\x01\x12\x14\n\x10\x44\x45\x41\x43TIVATE_ROUTE\x10\x02\x62\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'control_protocol_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  _CONTROLMESSAGE._serialized_start=33
  _CONTROLMESSAGE._serialized_end=397
  _CONTROLMESSAGE_MESSAGETYPE._serialized_start=296
  _CONTROLMESSAGE_MESSAGETYPE._serialized_end=397
  _NEIGHBORINFO._serialized_start=399
  _NEIGHBORINFO._serialized_end=526
  _FLOODINGMESSAGE._serialized_start=529
  _FLOODINGMESSAGE._serialized_end=827
  _FLOODINGMESSAGE_MESSAGETYPE._serialized_start=751
  _FLOODINGMESSAGE_MESSAGETYPE._serialized_end=827
# @@protoc_insertion_point(module_scope)
