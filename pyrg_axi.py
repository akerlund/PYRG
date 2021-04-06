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
import sys, os, re, math
import itertools, operator
from datetime import date

def sort_uniq(sequence):
  return map(operator.itemgetter(0),
             itertools.groupby(sorted(sequence)))

def generate_axi(yaml_file_path):

  this_path          = os.path.dirname(os.path.abspath(sys.argv[0]))
  axi_template_path  = this_path + "/templates/axi4_reg_slave.sv"
  header_file_path   = this_path + "/templates/header.txt"

  # ----------------------------------------------------------------------------
  # Loading in the templates
  # ----------------------------------------------------------------------------

  header = ""
  with open(header_file_path, 'r') as file:
    header = file.read()

  axi_template = ""
  with open(axi_template_path, 'r') as file:
    axi_template = file.read()

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
  # Creating all register classes and their uvm_reg_field's
  # ----------------------------------------------------------------------------

  # First information in the file
  BLOCK_NAME    = block_name
  BUS_BIT_WIDTH = block_contents['bus_width']

  # Variables for construction the AXI slave
  rtl_parameters       = [] # Size fields which are strings are considered parameters
  rtl_ports            = [] # We list all ports we generate as tuples (IO, PORT_WIDTH, FIELD_NAME)
  rtl_resets           = [] # If a reset value is specified for a register we add in this list

  rtl_cmd_registers    = [] # Save all 'cmd_' registers here, used later to set them to '0' as default
  all_rtl_writes       = "" # Contains the RTL writes
  all_rtl_reads        = "" # Contains the RTL reads
  all_mem_writes       = "" # Contains the MEM writes
  all_rc_registers     = [] # Contains the RC registers

  reg_all_fields       = [] # If a register contains 2 or more fields, we save them here because
                            # we need to finish iterating through all fields so we later can make the
                            # assignment like, e.g., "{f2, f1, f0} <= cif.wdata;"
  reg_rc_accessed      = {} # ReadAndClear registers
  reg_rc_declarations  = []
  reg_rom_declarations = []

  rtl_parameters.append("AXI_DATA_WIDTH_P")
  rtl_parameters.append("AXI_ADDR_WIDTH_P")
  rtl_parameters.append("AXI_ID_P")

  if ("parameters" in block_contents.keys()):
    for p in block_contents['parameters']:
      rtl_parameters.append(p)

  # ----------------------------------------------------------------------------
  # Iterating through the list of registers
  # ----------------------------------------------------------------------------
  for reg in block_contents['registers']:

    # Register information
    reg_name   = reg['name']
    reg_access = reg['access']
    if ("repeat" in reg.keys()):
      reg_repeat = reg["repeat"]
    else:
      reg_repeat = 1

    # Generate RTL code (for fields) are appended to these
    _reg_writes = []
    _reg_reads  = []

    # Check if this register has access type RC (Read and Clear)
    if (reg_access in ["RC"]):
      all_rc_registers.append(reg_name)
      reg_rc_accessed[reg_name] = []

    # --------------------------------------------------------------------------
    # Iterating through the fields
    # --------------------------------------------------------------------------
    for field in reg['bit_fields']:

      # Field variables
      _field_name    = field['field']['name']
      _field_size    = field['field']['size']
      _field_lsb_pos = field['field']['lsb_pos']
      _field_type    = _field_name.split("_")[0].upper() # Register have names, e.g., prefix_block_register

      # rtl_ports
      _port_width = ""
      if (reg_repeat > 1):
        _port_width += "[%s : 0] " % (reg_repeat - 1)
      if (isinstance(_field_size, str)): # If the size is a string, i.e., a constant
        _port_width += "[%s-1 : 0]" % (_field_size)
      elif (_field_size == 1):           # If the size is just one bit
        _port_width += " "
      else:                              # Else, any other integer
        _port_width += "[%s : 0]" % (str(_field_size-1))

      if (_field_type in ["CR", "CMD"]):
        rtl_ports.append(("    output logic ", _port_width, _field_name))
      elif (_field_type in ["SR", "IRQ"]):
        rtl_ports.append(("    input  wire  ", _port_width, _field_name))
      elif (_field_type in ["ROM"]):
        reg_rom_declarations.append((_port_width, _field_name, field['field']['reset_value'], _field_size))

      # Declaration of Read and Clear registers
      if (reg_access in ["RC"]):
        reg_rc_declarations.append((_port_width, _field_name))

      # rtl_resets
      if ("reset_value" in field['field'].keys() and not _field_type in ["ROM"]):
        rtl_resets.append((_field_name, field['field']['reset_value']))

      # rtl_cmd_registers
      if (_field_type in ["CMD"]):
        rtl_cmd_registers.append(_field_name)


      # Field assignments
      _axi_range = ""
      _wr_indent = 16
      _rd_indent = 8

      # If this register contains only one field
      if len(reg['bit_fields']) == 1:

        # Calculating the AXI range
        if (isinstance(_field_size, str)):
          # NOTE: The lsb position must be an integer
          if (_field_lsb_pos == 0):
            _axi_range = "%s-1 : 0" % (_field_size)
          else:
            _axi_range = "%s+%s-1 : %s" % (_field_size, _field_lsb_pos, _field_lsb_pos)
        # If the size is just one bit we do not have to define a range
        elif (_field_size == 1):
          _axi_range = _field_lsb_pos
        # Else, any other integer
        else:
          _axi_range = "%s : 0" % (str(_field_size-1))

        # Writes
        if (reg_access in ["WO", "RW"]):
          _write = _wr_indent*" " + _field_name + (" <= cif.wdata[%s]" % (_axi_range))
          _reg_writes.append(_write)

        # Reads
        if (reg_access in ["RO", "RW", "ROM"]):
          _read = _rd_indent*" " + ("cif.rdata[%s] = ") % (_axi_range) + _field_name
          _reg_reads.append(_read)

        # Read and Clear
        if (reg_access in ["RC"]):
          _read  = _rd_indent*" " + ("cif.rdata[%s] = ") % (_axi_range) + _field_name
          _read += _rd_indent*" " + "clear_" + reg_name + " <= '1"
          _reg_reads.append(_read)

      else:

        if (reg_access in ["RC"]):
          reg_rc_accessed[reg_name].append(_field_name)

      # If there are more than one fields we make assignments
      if (len(reg['bit_fields']) != 1) and not (reg_access in ["RC"]):
        reg_all_fields.append(_field_name)



    # </end> of field iteration



    # For register with more than one field we make assignments
    if len(reg_all_fields):

      # Reversing reg_all_fields so that the first fields is placed at the lowest bits
      _fields_concatenated = ', '.join(reg_all_fields[::-1])

      if (reg_access in ["WO", "RW"]):
        _write = _wr_indent*" " + "{" + _fields_concatenated + "} <= cif.wdata"
        _reg_writes.append(_write)

      if (reg_access in ["RO", "RW"]):
        _read = _rd_indent*" " + "cif.rdata = " + "{" + _fields_concatenated + "}"
        _reg_reads.append(_read)


      reg_all_fields = []

    # Read And Clear registers
    if reg_name in reg_rc_accessed.keys() and len(reg_rc_accessed[reg_name]):
      _fields_concatenated = ", ".join(reg_rc_accessed[reg_name][::-1])
      _read                = _rd_indent*" " + "cif.rdata = " + "{" + _fields_concatenated + "};\n"
      _read               += _rd_indent*" " + "clear_" + reg_name + " = '1"
      _reg_reads.append(_read)


    # Generating all the write and read fields
    _reg_address = "%s_ADDR" % (reg_name.upper())
    _wr_indent -= 2
    _rd_indent -= 2

    if len(_reg_writes):
      if (reg_repeat > 1):
        _wr_row = ""
        for i in range(reg_repeat):
          _reg_address = "%s_%d_ADDR" % (reg_name.upper(), i)
          _wr_row += _wr_indent*" " + _reg_address + ": begin\n"

          for wr in _reg_writes:
            _wr_row += wr + ";\n"
          _wr_row += _wr_indent*" " + "end\n\n"
      else:

        _wr_row = _wr_indent*" " + _reg_address + ": begin\n"
        for wr in _reg_writes:
          _wr_row += wr + ";\n"

        _wr_row += _wr_indent*" " + "end\n\n"
      _reg_writes = []
      all_rtl_writes += _wr_row

    if len(_reg_reads):
      if (reg_repeat > 1):
        _rd_row = ""
        for i in range(reg_repeat):
          _reg_address = "%s_%d_ADDR" % (reg_name.upper(), i)
          _rd_row += _rd_indent*" " + _reg_address + ": begin\n"

          for rd in _reg_reads:
            _rd_row += rd + "[%d];\n" % i
          _rd_row += _rd_indent*" " + "end\n\n"
      else:

        _rd_row = _rd_indent*" " + _reg_address + ": begin\n"
        for rd in _reg_reads:
          _rd_row += rd + ";\n"
        _rd_row += _rd_indent*" " + "end\n\n"
      _reg_reads = []
      all_rtl_reads  += _rd_row



  # </end> of register iteration



  RC_DEFAULT = ""
  for rc in all_rc_registers:
    rtl_ports.append(("    output logic ", " ", "clear_" + rc))
    RC_DEFAULT += 4*" " + "clear_" + rc + " = '0;\n"



  # Iterating through the list of memories
  MEMORIES = ""
  if ('memories' in block_contents.keys()):

    for mem in block_contents['memories']:
      mem_name   = mem['name']
      mem_access = mem['access']
      mem_size   = mem['size']
      mem_width  = mem['width']

      # rtl_ports

      # In order to use the "awaddr" as the address for memory, we need to add
      # extra bits because the slave will increase the address by
      # (BUS_BIT_WIDTH/8) for every beat. Therefore, e.g., for a 64-bit data
      # bus, a counter's values will essentially be present in the higher bits.
      _byte_addr_width = math.log2(BUS_BIT_WIDTH/8)
      _port_addr_width = "[%d : 0]" % (math.log2(mem_size) - 1 + _byte_addr_width)
      _port_data_width = "[%d : 0]" % (mem_width-1)
      rtl_ports.append(("    output logic ", " ", mem_name + "_we"))
      rtl_ports.append(("    output logic ", _port_addr_width, mem_name + "_addr"))
      rtl_ports.append(("    output logic ", _port_data_width, mem_name + "_wdata"))

      # rtl_resets
      rtl_resets.append((mem_name + "_we", 0))
      rtl_resets.append((mem_name + "_addr", 0))
      rtl_resets.append((mem_name + "_wdata", 0))

      MEMORIES += 6*" " + "%s_we    <= '0;\n" % (mem_name)
      MEMORIES += 6*" " + "%s_addr  <= '0;\n" % (mem_name)
      MEMORIES += 6*" " + "%s_wdata <= '0;\n" % (mem_name)

      # all_mem_writes
      _mem_addr = "%s_%s_BASE_ADDR" % (BLOCK_NAME.upper(), mem_name.upper())
      _mem_last_addr = "%s_%s_HIGH_ADDR" % (BLOCK_NAME.upper(), mem_name.upper())

      if (mem_access in ["RW", "WO"]):
        all_mem_writes += 12*" " + "if (awaddr_r0 >= %s && awaddr_r0 <= %s) begin\n" % (_mem_addr, _mem_last_addr)
        all_mem_writes += 14*" " + "%s_we    <= '1;\n" % (mem_name)
        all_mem_writes += 14*" " + "%s_addr  <= awaddr_r0%s;\n" % (mem_name, _port_addr_width)
        all_mem_writes += 14*" " + "%s_wdata <= cif.wdata%s;\n" % (mem_name, _port_data_width)
        all_mem_writes += 12*" " + "end\n\n"

      # ------------------------------------------------------------------------
      # all_mem_reads
      # ------------------------------------------------------------------------
      if (mem_access in ["RW", "RO"]):
        raise Exception("Only writable memories supported yet!")


  # rtl_ports
  longest = 0 # Find the longest declaration for indenting nice
  for port in rtl_ports:
    (_, _field_size, _) = port
    if (len(_field_size) > longest):
      longest = len(_field_size)

  AXI_PORTS = ""
  for port in rtl_ports:
    (IO, _field_size, _field_name) = port
    AXI_PORTS += IO + _field_size.rjust(longest, " ") + " " + _field_name + ",\n"
  AXI_PORTS = AXI_PORTS[:-2] # Remove the last comma and newline


  # reg_rc_declarations and reg_rom_declarations
  longest = 0
  for reg in reg_rc_declarations:
    (_port_width, _field_name) = reg
    if (len(_port_width) > longest):
      longest = len(_port_width)

  for reg in reg_rom_declarations:
    (_port_width, _field_name, _, _) = reg
    if (len(_port_width) > longest):
      longest = len(_port_width)

  LOGIC_DECLARATIONS = "\n"
  for reg in reg_rom_declarations:
    (_port_width, _field_name, _reset_value, _field_size) = reg
    LOGIC_DECLARATIONS += "  localparam logic unsigned " + _port_width.rjust(longest, " ") + " " + _field_name + (" = ") + _reset_value + ";\n"


  # rtl_resets
  longest = 0
  for port in rtl_resets:
    (_field_name, _) = port
    if (len(_field_name) > longest):
      longest = len(_field_name)
  AXI_RESET = ""
  for port in rtl_resets:
    (_field_name, _field_reset_value) = port
    AXI_RESET += 6*" " + _field_name.ljust(longest, " ") + " <= " + str(_field_reset_value) + ";\n"


  # rtl_cmd_registers
  longest = 0
  for cmd in rtl_cmd_registers:
    if (len(cmd) > longest):
      longest = len(cmd)
  CMD_DEFAULT = "\n"
  for cmd in rtl_cmd_registers:
    CMD_DEFAULT += 6*" " + cmd.ljust(longest, " ") + " <= '0;\n"


  PARAMETERS = ""
  _re = r".*\$.*\((.*)\)"
  for i in range(len(rtl_parameters)):
    match = re.match(_re, str(rtl_parameters[i]))
    if match:
      rtl_parameters[i] = match.group(1)
  rtl_parameters = sort_uniq(rtl_parameters)
  for p in rtl_parameters:
    PARAMETERS += 4*' ' + "parameter int %s = -1,\n" % p
  PARAMETERS = PARAMETERS[:-2]


  output = header + axi_template
  output = output.replace("IMPORT",             ("import " + BLOCK_NAME + "_address_pkg::*;"))
  output = output.replace("PARAMETERS",         PARAMETERS)
  output = output.replace("CLASS_NAME",         (BLOCK_NAME + "_axi_slave"))
  output = output.replace("PORTS",              AXI_PORTS)
  output = output.replace("LOGIC_DECLARATIONS", LOGIC_DECLARATIONS)
  output = output.replace("CMD_REGISTERS",      CMD_DEFAULT)
  output = output.replace("MEM_INTERFACES",     MEMORIES)
  output = output.replace("RESETS",             AXI_RESET)
  output = output.replace("AXI_WRITES",         all_rtl_writes)
  output = output.replace("AXI_MEM_WRITES",     all_mem_writes)
  output = output.replace("RC_DEFAULT",         RC_DEFAULT)
  output = output.replace("AXI_READS",          all_rtl_reads)

  # Write the AXI slave to file
  output_path = '/'.join(yaml_file_path.split('/')[:-2]) + "/rtl/"
  output_file = output_path + BLOCK_NAME + "_axi_slave.sv"
  with open(output_file, 'w') as file:
    file.write(output)

  print("INFO [pyrg] Generated %s" % output_file)
