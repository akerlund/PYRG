#!/usr/bin/env python3

################################################################################
##
## Copyright (C) 2020 Fredrik Åkerlund
##
## This program is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see <https:##www.gnu.org/licenses/>.
##
## Description: Demonstrating how a yaml file with information about registers
## can be parsed and printed.
##
################################################################################

import yaml
import sys, os, math
from datetime import date

def generate_uvm(yaml_file_path, uvm_path, bus_bit_width = 64, addr_width = 16):

  this_path           = os.path.dirname(os.path.abspath(sys.argv[0]))
  uvm_reg_file_path   = this_path + "/templates/uvm_reg.sv"
  uvm_block_file_path = this_path + "/templates/uvm_block.sv"
  field_template_path = this_path + "/templates/reg_field.sv"
  header_file_path    = this_path + "/templates/header.txt"

  rtl_path = '/'.join(yaml_file_path.split('/')[:-2]) + "/rtl/"
  sw_path  = '/'.join(yaml_file_path.split('/')[:-2]) + "/sw/"

  # If the used did not specify a specific path for the UVM files, this is default
  if (not len(uvm_path)):
    uvm_path = '/'.join(yaml_file_path.split('/')[:-2]) + "/tb/uvm_reg/"

  if not os.path.exists(rtl_path):
      os.makedirs(rtl_path)

  if not os.path.exists(uvm_path):
      os.makedirs(uvm_path)

  if not os.path.exists(sw_path):
      os.makedirs(sw_path)

  # ----------------------------------------------------------------------------
  # Loading in the templates
  # ----------------------------------------------------------------------------

  uvm_reg = ""
  with open(uvm_reg_file_path, 'r') as file:
    uvm_reg = file.read()

  uvm_block = ""
  with open(uvm_block_file_path, 'r') as file:
    uvm_block = file.read()

  header = ""
  with open(header_file_path, 'r') as file:
    header = file.read()

  field_template = ""
  with open(field_template_path, 'r') as file:
    field_template = file.read()

  # ----------------------------------------------------------------------------
  # Loading in the YAML file and the UVM templates
  # ----------------------------------------------------------------------------

  # Variables for storing the YAML file contents
  block_name     = None
  block_contents = None

  with open(yaml_file_path, 'r') as file:

    yaml_reg = yaml.load(file, Loader = yaml.FullLoader)

    block_name, block_contents = list(yaml_reg.items())[0]

  # ----------------------------------------------------------------------------
  # PART 1
  # Creating all register classes and their uvm_reg_field's
  # ----------------------------------------------------------------------------

  # First information in the file
  BLOCK_NAME    = block_name
  BASE_ADDR     = "0"
  BUS_BIT_WIDTH = block_contents['bus_width']
  ACRONYM       = BLOCK_NAME.upper()

  # Variable used
  UVM_BUILD              = ""

  register_names         = [] # Used later to generate the register block
  address_map            = []
  c_address_map          = []

  # We are saving the generated "uvm_reg" classes in this variable
  reg_classes = header


  # Iterating through the list of registers
  for reg in block_contents['registers']:

    reg_name   = reg['name']
    reg_access = "\"" + reg['access'] + "\""
    reg_class  = uvm_reg.replace("CLASS_DESCRIPTION", reg['desc'])
    if ("repeat" in reg.keys()):
      reg_repeat = reg["repeat"]
      _ri = "_0" # Repeat suffix of names
    else:
      reg_repeat = 1
      _ri        = ""

    if reg_repeat > 1:
      for i in range(reg_repeat):
        register_names.append((reg_name+_ri, reg_access))
        address_map.append("  localparam logic [%d : 0] %s_%d_ADDR" % (addr_width-1, reg_name.upper(), i))
        c_address_map.append("  #define %s_%d_ADDR" % (reg_name.upper(), i))
        _ri = "_" + str(i+1)
      _ri = "_0"
    else:
      register_names.append((reg_name, reg_access))
      address_map.append("  localparam logic [%d : 0] %s_ADDR" % (addr_width-1, reg_name.upper()))
      c_address_map.append("  #define %s_ADDR" % (reg_name.upper()))

    reg_field_declarations = ""

    _reg_total_size = ""

    # Generating the fields of the register
    for i in range(reg_repeat):

      for field in reg['bit_fields']:

        reg_field_declarations += "  rand uvm_reg_field %s%s;\n" % (field['field']['name'], _ri)

        _field_instance    = "%s%s = uvm_reg_field::type_id::create(\"%s%s\");" % (field['field']['name'], _ri, field['field']['name'], _ri)
        _field_description = field['field']['description']
        _field_name        = field['field']['name'] + _ri
        _field_size        = str(field['field']['size'])
        _field_lsb_pos     = str(field['field']['lsb_pos'])
        _reg_total_size   += _field_size+"+"

        _reg_field = field_template
        _reg_field = _reg_field.replace("FIELD_INSTANCE",    _field_instance)
        _reg_field = _reg_field.replace("FIELD_DESCRIPTION", _field_description)
        _reg_field = _reg_field.replace("FIELD_NAME",        _field_name)
        _reg_field = _reg_field.replace("FIELD_SIZE",        _field_size)
        _reg_field = _reg_field.replace("FIELD_LSB_POS",     _field_lsb_pos)
        _reg_field = _reg_field.replace("FIELD_ACCESS",      reg_access)


        if ("reset_value" in field['field'].keys()):
          _reg_field = _reg_field.replace("FIELD_RESET",     str(field['field']['reset_value']))
          _reg_field = _reg_field.replace("FIELD_HAS_RESET", str(1))
        else:
          _reg_field = _reg_field.replace("FIELD_RESET",     str(0))
          _reg_field = _reg_field.replace("FIELD_HAS_RESET", str(0))

        UVM_BUILD += _reg_field



      reg_class = reg_class.replace("REG_NAME",               (reg_name + _ri + "_reg"))
      reg_class = reg_class.replace("UVM_FIELD_DECLARATIONS", reg_field_declarations)
      reg_class = reg_class.replace("UVM_REG_SIZE",           _reg_total_size[:-1]) # Not all bits need to be implemented.
      reg_class = reg_class.replace("UVM_BUILD",              UVM_BUILD)

      reg_classes += reg_class
      UVM_BUILD    = ""

      if reg_repeat > 1:
        reg_class  = uvm_reg.replace("CLASS_DESCRIPTION", reg['desc'])
        reg_field_declarations = ""
        _reg_total_size = ""
        _ri = "_" + str(i+1)

  # Write the register classes to file
  output_file = uvm_path + BLOCK_NAME + "_reg.sv"
  with open(output_file, 'w') as file:
    file.write(reg_classes)

  print("INFO [pyrg] Generated %s" % output_file)

  # ----------------------------------------------------------------------------
  # PART 2.0
  # Parsing memories
  # ----------------------------------------------------------------------------

  sv_memories = []
  c_memories  = []

  # Iterating through the list of memories
  if ('memories' in block_contents.keys()):

    for mem in block_contents['memories']:

      # Memory information
      mem_name   = mem['name']
      mem_access = mem['access']
      mem_size   = mem['size']

      _mem_base_addr = "  localparam logic [%d : 0] %s_%s_BASE_ADDR = " % (addr_width-1, ACRONYM, mem_name.upper())
      _mem_high_addr = "  localparam logic [%d : 0] %s_%s_HIGH_ADDR = " % (addr_width-1, ACRONYM, mem_name.upper())
      sv_memories.append((mem_size, _mem_base_addr, _mem_high_addr))

      _mem_base_addr = "  #define %s_%s_BASE_ADDR " % (ACRONYM, mem_name.upper())
      _mem_high_addr = "  #define %s_%s_HIGH_ADDR " % (ACRONYM, mem_name.upper())
      c_memories.append((mem_size, _mem_base_addr, _mem_high_addr))

      # ------------------------------------------------------------------------
      # all_mem_reads
      # ------------------------------------------------------------------------
      if (mem_access in ["RW", "R"]):
        raise Exception("Only writable memories supported yet!")



  # ----------------------------------------------------------------------------
  # PART 2.1
  # Creating the System Verilog address map
  # ----------------------------------------------------------------------------

  _bus_bytes = int(bus_bit_width/8)

  longest_name = 0
  for addr in address_map:
    if len(addr) > longest_name:
      longest_name = len(addr)

  _i = 0
  for i in range(len(address_map)):
    address_map[i] = address_map[i].ljust(longest_name, " ") + (" = %d'h" % (addr_width)) + str(hex(i*_bus_bytes)[2:].zfill(4)).upper() + ";\n"
    _i = i

  ADDRESS_HIGH = (("  localparam logic [%d : 0] " % (addr_width-1)) + ACRONYM + "_HIGH_ADDRESS").ljust(longest_name, " ") + (" = %d'h" % (addr_width)) + str(hex(len(address_map)*_bus_bytes)[2:].zfill(4)).upper() + ";\n"

  # Adding memories and aligning the lower bits to the size of the memory as the address field of the interface
  # is used, too
  _latex = []
  _aligned_mem_addr = len(address_map) * _bus_bytes
  for m in sv_memories:
    (mem_size, _mem_base_addr, _mem_high_addr) = m
    mem_size_log2  = int(math.ceil(math.log2(mem_size)))
    bus_bytes_log2 = int(math.ceil(math.log2(_bus_bytes)))

    # The first '1' in the address must begin after:
    # - bus_bytes_log2: Because we are using the address as a counter, the lower bits increase by (AXI_DATA_WIDTH_P/8) in the slave
    # - mem_size_log2: Because these bits will have the counting value
    _aligned_mem_addr = ((_aligned_mem_addr + 2**(mem_size_log2+bus_bytes_log2)) >> (mem_size_log2+bus_bytes_log2)) << (mem_size_log2+bus_bytes_log2)
    _latex.append((str(hex(_aligned_mem_addr)[2:].zfill(4)).upper(),
                   str(hex(_aligned_mem_addr + mem_size * _bus_bytes)[2:].zfill(4)).upper())
                 )
    address_map.append(_mem_base_addr + ("%d'h" % (addr_width)) + str(hex(_aligned_mem_addr)[2:].zfill(4)).upper() + ";\n")
    address_map.append(_mem_high_addr + ("%d'h" % (addr_width)) + str(hex(_aligned_mem_addr + mem_size * _bus_bytes)[2:].zfill(4)).upper() + ";\n")
    _aligned_mem_addr += mem_size * _bus_bytes


  pkt_top  = "\n"
  pkt_top += "`ifndef %s\n"   % (BLOCK_NAME.upper() + "_ADDRESS_PKG")
  pkt_top += "`define %s\n" % (BLOCK_NAME.upper() + "_ADDRESS_PKG")
  pkt_top += "\n"
  pkt_top += "package %s;\n\n" % (BLOCK_NAME + "_address_pkg")

  pkt_bot  = "\n\n"
  pkt_bot  = "\nendpackage\n\n`endif\n"

  output_file = rtl_path + BLOCK_NAME + "_address_pkg.sv"
  with open(output_file, 'w') as file:
    file.write(header)
    file.write(pkt_top)
    file.write(ADDRESS_HIGH)
    file.write(''.join(address_map))
    file.write(pkt_bot)

  print("INFO [pyrg] Generated %s" % output_file)




  # ----------------------------------------------------------------------------
  # PART 2.2
  # Creating the C address map
  # ----------------------------------------------------------------------------

  longest_name = 0
  for addr in c_address_map:
    if len(addr) > longest_name:
      longest_name = len(addr)

  for i in range(len(c_address_map)):
    c_address_map[i] = c_address_map[i].ljust(longest_name, " ") +\
                       " " + ACRONYM + "_PHYSICAL_ADDRESS_C +" + " 0x%s\n" % str(hex(i*_bus_bytes)[2:].zfill(4)).upper()

  ADDRESS_HIGH = ("  #define " + ACRONYM + "_HIGH_ADDRESS").ljust(longest_name, " ") +\
                  " " + ACRONYM + "_PHYSICAL_ADDRESS_C +" + " 0x%s\n" % str(hex(len(c_address_map)*_bus_bytes)[2:].zfill(4)).upper()

  # Adding memories and aligning the lower bits to the size of the memory as the address field of the interface
  # is used, too
  _aligned_mem_addr = len(c_address_map) * _bus_bytes
  for m in c_memories:
    (mem_size, _mem_base_addr, _mem_high_addr) = m
    mem_size_log2 = int(math.ceil(math.log2(mem_size)))
    _aligned_mem_addr = ((_aligned_mem_addr + 2**(mem_size_log2+bus_bytes_log2)) >> (mem_size_log2+bus_bytes_log2)) << (mem_size_log2+bus_bytes_log2)
    c_address_map.append(_mem_base_addr + ACRONYM + "_PHYSICAL_ADDRESS_C +" + " 0x%s\n" % str(hex(_aligned_mem_addr))[2:].zfill(4).upper())
    c_address_map.append(_mem_high_addr + ACRONYM + "_PHYSICAL_ADDRESS_C +" + " 0x%s\n" % str(hex(_aligned_mem_addr + mem_size * _bus_bytes))[2:].zfill(4).upper())
    _aligned_mem_addr += mem_size * _bus_bytes

  pkt_top  = ""
  pkt_top += "#ifndef %s\n" % (BLOCK_NAME.upper() + "_ADDRESS_H")
  pkt_top += "#define %s\n" % (BLOCK_NAME.upper() + "_ADDRESS_H")
  pkt_top += "\n"

  pkt_bot  = "\n#endif\n"

  output_file = sw_path + BLOCK_NAME + "_address.h"
  with open(output_file, 'w') as file:
    file.write(header)
    file.write(pkt_top)
    file.write(ADDRESS_HIGH)
    file.write(''.join(c_address_map))
    file.write(pkt_bot)

  print("INFO [pyrg] Generated %s" % output_file)





  # ----------------------------------------------------------------------------
  # PART 3
  # Creating the register block
  # ----------------------------------------------------------------------------

  UVM_REG_DECLARATIONS = ""
  UVM_BUILD            = ""
  UVM_ADD              = ""
  offset   = 0
  MAP_NAME = "\"" + BLOCK_NAME + "_map\""

  for (reg, access) in register_names:

    UVM_REG_DECLARATIONS += "  rand %s_reg %s;\n" % (reg, reg)

    UVM_BUILD += "    %s = %s_reg::type_id::create(\"%s\");\n" % (reg, reg, reg)
    UVM_BUILD += "    %s.build();\n" % (reg)
    UVM_BUILD += "    %s.configure(this);\n\n" % (reg)

    _access = ""
    if 'R' in access:
      if 'W' in access:
        _access = "\"RW\""
      else:
        _access = "\"RO\""
    else:
      _access = "\"WO\""

    UVM_ADD += "    default_map.add_reg(%s, %d, %s);\n" % (reg, offset, _access)

    offset += int(BUS_BIT_WIDTH/8)

  block = header + uvm_block
  block = block.replace("CLASS_NAME",           (BLOCK_NAME + "_block"))
  block = block.replace("UVM_REG_DECLARATIONS", UVM_REG_DECLARATIONS)
  block = block.replace("UVM_BUILD",            UVM_BUILD)
  block = block.replace("MAP_NAME",             MAP_NAME)
  block = block.replace("BASE_ADDR",            BASE_ADDR)
  block = block.replace("BUS_BIT_WIDTH",        str(int(BUS_BIT_WIDTH/8)))
  block = block.replace("UVM_ADD",              UVM_ADD)


  # Write the register block to file
  output_file = uvm_path + BLOCK_NAME + "_block.sv"
  with open(output_file, 'w') as file:
    file.write(block)

  print("INFO [pyrg] Generated %s" % output_file)

  return(_latex)
