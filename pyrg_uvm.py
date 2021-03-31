#!/usr/bin/env python3

################################################################################
##
## Copyright (C) 2020 Fredrik Åkerlund
## https://github.com/akerlund/PYRG
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

def generate_uvm(yaml_file_path, git_root, addr_width = 16):

  this_path           = os.path.dirname(os.path.abspath(sys.argv[0]))
  uvm_reg_file_path   = this_path + "/templates/uvm_reg.sv"
  uvm_block_file_path = this_path + "/templates/uvm_block.sv"
  field_template_path = this_path + "/templates/reg_field.sv"
  header_file_path    = this_path + "/templates/header.txt"

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
  top_name    = None
  yml_entries = None

  with open(yaml_file_path, 'r') as file:
    yaml_reg              = yaml.load(file, Loader = yaml.FullLoader)
    top_name, yml_entries = list(yaml_reg.items())[0]

  # ----------------------------------------------------------------------------
  # Extracting the user defined paths
  # ----------------------------------------------------------------------------

  rtl_path = yml_entries["rtl_path"].replace("$GIT_ROOT", git_root)
  uvm_path = yml_entries["uvm_path"].replace("$GIT_ROOT", git_root)
  sw_path  = yml_entries["sw_path"].replace("$GIT_ROOT",  git_root)

  if not os.path.exists(rtl_path):
    os.makedirs(rtl_path)

  if not os.path.exists(uvm_path):
    os.makedirs(uvm_path)

  if not os.path.exists(sw_path):
    os.makedirs(sw_path)

  # ----------------------------------------------------------------------------
  # PART 1
  # Creating all register classes (uvm_reg) and their fields (uvm_reg_field).
  # We are also creating the constants (SV) and defines (C) for the register's
  # addresses. Each register's name is saved in a list which is used later to
  # create the register slave's block (uvm_reg_block).
  # ----------------------------------------------------------------------------

  reg_classes    = header
  register_names = [] # Tuple list
  sv_address_map = [] # localparams
  c_address_map  = [] # defines

  # Iterating through the list of registers
  for reg in yml_entries['registers']:

    _reg_name   = reg['name']
    _reg_access = "\"" + reg['access'] + "\""
    _reg_class  = uvm_reg.replace("CLASS_DESCRIPTION", reg['desc'])
    _reg_block_body = ""

    # Registers can be repeated with the same name but different numeric suffix
    if ("repeat" in reg.keys()):
      _reg_repeat = reg["repeat"]
      _ri         = "_0" # Repeat index
    else:
      _reg_repeat = 1
      _ri         = ""

    if _reg_repeat > 1:
      for i in range(_reg_repeat):
        register_names.append((_reg_name+_ri, _reg_access))
        sv_address_map.append("  localparam logic [%d : 0] %s_%d_ADDR" % (addr_width-1, _reg_name.upper(), i))
        c_address_map.append("  #define %s_%d_ADDR" % (_reg_name.upper(), i))
        _ri = "_" + str(i+1)
      _ri = "_0"
    else:
      register_names.append((_reg_name, _reg_access))
      sv_address_map.append("  localparam logic [%d : 0] %s_ADDR" % (addr_width-1, _reg_name.upper()))
      c_address_map.append("  #define %s_ADDR" % (_reg_name.upper()))

    _reg_field_declarations = ""
    _reg_total_size        = ""

    # Generating the fields (uvm_reg_field) of the register
    for i in range(_reg_repeat):

      for field in reg['bit_fields']:

        _reg_field_declarations += "  rand uvm_reg_field %s%s;\n" % (field['field']['name'], _ri)

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
        _reg_field = _reg_field.replace("FIELD_ACCESS",      _reg_access)

        if ("reset_value" in field['field'].keys()):
          _reg_field = _reg_field.replace("FIELD_RESET",     str(field['field']['reset_value']))
          _reg_field = _reg_field.replace("FIELD_HAS_RESET", str(1))
        else:
          _reg_field = _reg_field.replace("FIELD_RESET",     str(0))
          _reg_field = _reg_field.replace("FIELD_HAS_RESET", str(0))

        _reg_block_body += _reg_field



      _reg_class = _reg_class.replace("REG_NAME",               (_reg_name + _ri + "_reg"))
      _reg_class = _reg_class.replace("UVM_FIELD_DECLARATIONS", _reg_field_declarations)
      _reg_class = _reg_class.replace("UVM_REG_SIZE",           _reg_total_size[:-1]) # Not all bits need to be implemented.
      _reg_class = _reg_class.replace("UVM_BUILD",              _reg_block_body)

      reg_classes += _reg_class
      _reg_block_body    = ""

      if _reg_repeat > 1:
        _reg_class  = uvm_reg.replace("CLASS_DESCRIPTION", reg['desc'])
        _reg_field_declarations = ""
        _reg_total_size         = ""
        _ri                     = "_" + str(i+1)

  # Write the register classes to file
  output_file = uvm_path + '/' + top_name + "_reg.sv"
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
  if ('memories' in yml_entries.keys()):

    for mem in yml_entries['memories']:

      # Memory information
      mem_name   = mem['name']
      mem_access = mem['access']
      mem_size   = mem['size']

      _mem_base_addr = "  localparam logic [%d : 0] %s_%s_BASE_ADDR = " % (addr_width-1, top_name.upper(), mem_name.upper())
      _mem_high_addr = "  localparam logic [%d : 0] %s_%s_HIGH_ADDR = " % (addr_width-1, top_name.upper(), mem_name.upper())
      sv_memories.append((mem_size, _mem_base_addr, _mem_high_addr))

      _mem_base_addr = "  #define %s_%s_BASE_ADDR " % (top_name.upper(), mem_name.upper())
      _mem_high_addr = "  #define %s_%s_HIGH_ADDR " % (top_name.upper(), mem_name.upper())
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

  _bus_bytes = int(yml_entries['bus_width']/8)

  longest_name = 0
  for addr in sv_address_map:
    if len(addr) > longest_name:
      longest_name = len(addr)

  _i = 0
  for i in range(len(sv_address_map)):
    sv_address_map[i] = sv_address_map[i].ljust(longest_name, " ") + (" = %d'h" % (addr_width)) + str(hex(i*_bus_bytes)[2:].zfill(4)).upper() + ";\n"
    _i = i

  ADDRESS_HIGH = (("  localparam logic [%d : 0] " % (addr_width-1)) + top_name.upper() + "_HIGH_ADDRESS").ljust(longest_name, " ") + (" = %d'h" % (addr_width)) + str(hex(len(sv_address_map)*_bus_bytes)[2:].zfill(4)).upper() + ";\n"

  # Adding memories and aligning the lower bits to the size of the memory as the address field of the interface
  # is used, too
  _latex = []
  _aligned_mem_addr = len(sv_address_map) * _bus_bytes
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
    sv_address_map.append(_mem_base_addr + ("%d'h" % (addr_width)) + str(hex(_aligned_mem_addr)[2:].zfill(4)).upper() + ";\n")
    sv_address_map.append(_mem_high_addr + ("%d'h" % (addr_width)) + str(hex(_aligned_mem_addr + mem_size * _bus_bytes)[2:].zfill(4)).upper() + ";\n")
    _aligned_mem_addr += mem_size * _bus_bytes


  pkt_top  = "\n"
  pkt_top += "`ifndef %s\n"   % (top_name.upper() + "_ADDRESS_PKG")
  pkt_top += "`define %s\n" % (top_name.upper() + "_ADDRESS_PKG")
  pkt_top += "\n"
  pkt_top += "package %s;\n\n" % (top_name + "_address_pkg")

  pkt_bot  = "\n\n"
  pkt_bot  = "\nendpackage\n\n`endif\n"

  output_file = rtl_path + '/' + top_name + "_address_pkg.sv"
  with open(output_file, 'w') as file:
    file.write(header)
    file.write(pkt_top)
    file.write(ADDRESS_HIGH)
    file.write(''.join(sv_address_map))
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
                       " " + top_name.upper() + "_PHYSICAL_ADDRESS_C +" + " 0x%s\n" % str(hex(i*_bus_bytes)[2:].zfill(4)).upper()

  ADDRESS_HIGH = ("  #define " + top_name.upper() + "_HIGH_ADDRESS").ljust(longest_name, " ") +\
                  " " + top_name.upper() + "_PHYSICAL_ADDRESS_C +" + " 0x%s\n" % str(hex(len(c_address_map)*_bus_bytes)[2:].zfill(4)).upper()

  # Adding memories and aligning the lower bits to the size of the memory as the address field of the interface
  # is used, too
  _aligned_mem_addr = len(c_address_map) * _bus_bytes
  for m in c_memories:
    (mem_size, _mem_base_addr, _mem_high_addr) = m
    mem_size_log2 = int(math.ceil(math.log2(mem_size)))
    _aligned_mem_addr = ((_aligned_mem_addr + 2**(mem_size_log2+bus_bytes_log2)) >> (mem_size_log2+bus_bytes_log2)) << (mem_size_log2+bus_bytes_log2)
    c_address_map.append(_mem_base_addr + top_name.upper() + "_PHYSICAL_ADDRESS_C +" + " 0x%s\n" % str(hex(_aligned_mem_addr))[2:].zfill(4).upper())
    c_address_map.append(_mem_high_addr + top_name.upper() + "_PHYSICAL_ADDRESS_C +" + " 0x%s\n" % str(hex(_aligned_mem_addr + mem_size * _bus_bytes))[2:].zfill(4).upper())
    _aligned_mem_addr += mem_size * _bus_bytes

  pkt_top  = ""
  pkt_top += "#ifndef %s\n" % (top_name.upper() + "_ADDRESS_H")
  pkt_top += "#define %s\n" % (top_name.upper() + "_ADDRESS_H")
  pkt_top += "\n"

  pkt_bot  = "\n#endif\n"

  output_file = sw_path + '/' + top_name + "_address.h"
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
  reg_block_body            = ""
  UVM_ADD              = ""
  offset   = 0
  MAP_NAME = "\"" + top_name + "_map\""

  for (reg, access) in register_names:

    UVM_REG_DECLARATIONS += "  rand %s_reg %s;\n" % (reg, reg)

    reg_block_body += "    %s = %s_reg::type_id::create(\"%s\");\n" % (reg, reg, reg)
    reg_block_body += "    %s.build();\n" % (reg)
    reg_block_body += "    %s.configure(this);\n\n" % (reg)

    _access = ""
    if 'R' in access:
      if 'W' in access:
        _access = "\"RW\""
      else:
        _access = "\"RO\""
    else:
      _access = "\"WO\""

    UVM_ADD += "    default_map.add_reg(%s, %d, %s);\n" % (reg, offset, _access)

    offset += int(yml_entries['bus_width']/8)

  block = header + uvm_block
  block = block.replace("CLASS_NAME",           (top_name + "_block"))
  block = block.replace("UVM_REG_DECLARATIONS", UVM_REG_DECLARATIONS)
  block = block.replace("UVM_BUILD",            reg_block_body)
  block = block.replace("MAP_NAME",             MAP_NAME)
  block = block.replace("BASE_ADDR",            "0")
  block = block.replace("BUS_BIT_WIDTH",        str(int(yml_entries['bus_width']/8)))
  block = block.replace("UVM_ADD",              UVM_ADD)


  # Write the register block to file
  output_file = uvm_path + '/' + top_name + "_block.sv"
  with open(output_file, 'w') as file:
    file.write(block)

  print("INFO [pyrg] Generated %s" % output_file)

  return(_latex)
