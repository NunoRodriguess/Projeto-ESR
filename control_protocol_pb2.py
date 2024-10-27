# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: control_protocol.proto
# Protobuf Python Version: 5.28.2
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    28,
    2,
    '',
    'control_protocol.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x16\x63ontrol_protocol.proto\x12\x04node\"\xb6\x02\n\x0e\x43ontrolMessage\x12.\n\x04type\x18\x01 \x01(\x0e\x32 .node.ControlMessage.MessageType\x12\x0f\n\x07node_ip\x18\x02 \x01(\t\x12\x0f\n\x07node_id\x18\x03 \x01(\t\x12\x11\n\tnode_type\x18\x04 \x01(\t\x12%\n\tneighbors\x18\x05 \x03(\x0b\x32\x12.node.NeighborInfo\x12\x14\n\x0c\x63ontrol_port\x18\x06 \x01(\x05\x12\x11\n\tdata_port\x18\x07 \x01(\x05\"o\n\x0bMessageType\x12\x0c\n\x08REGISTER\x10\x00\x12\x15\n\x11REGISTER_RESPONSE\x10\x01\x12\x08\n\x04PING\x10\x02\x12\x08\n\x04PONG\x10\x03\x12\x14\n\x10UPDATE_NEIGHBORS\x10\x04\x12\x11\n\rINACTIVE_NODE\x10\x05\"l\n\x0cNeighborInfo\x12\x0f\n\x07node_id\x18\x01 \x01(\t\x12\x0f\n\x07node_ip\x18\x02 \x01(\t\x12\x11\n\tnode_type\x18\x03 \x01(\t\x12\x14\n\x0c\x63ontrol_port\x18\x04 \x01(\x05\x12\x11\n\tdata_port\x18\x05 \x01(\x05\"7\n\x0e\x43ontentRequest\x12\x12\n\ncontent_id\x18\x01 \x01(\t\x12\x11\n\tclient_id\x18\x02 \x01(\t\"M\n\x0f\x43ontentResponse\x12\x12\n\ncontent_id\x18\x01 \x01(\t\x12\x11\n\tsource_ip\x18\x02 \x01(\t\x12\x13\n\x0bsource_port\x18\x03 \x01(\x05\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'control_protocol_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_CONTROLMESSAGE']._serialized_start=33
  _globals['_CONTROLMESSAGE']._serialized_end=343
  _globals['_CONTROLMESSAGE_MESSAGETYPE']._serialized_start=232
  _globals['_CONTROLMESSAGE_MESSAGETYPE']._serialized_end=343
  _globals['_NEIGHBORINFO']._serialized_start=345
  _globals['_NEIGHBORINFO']._serialized_end=453
  _globals['_CONTENTREQUEST']._serialized_start=455
  _globals['_CONTENTREQUEST']._serialized_end=510
  _globals['_CONTENTRESPONSE']._serialized_start=512
  _globals['_CONTENTRESPONSE']._serialized_end=589
# @@protoc_insertion_point(module_scope)
