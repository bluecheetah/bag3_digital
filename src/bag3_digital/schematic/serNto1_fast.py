# BSD 3-Clause License
#
# Copyright (c) 2018, Regents of the University of California
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# -*- coding: utf-8 -*-

from typing import Mapping, Any

import pkg_resources
from pathlib import Path

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param

from pybag.enum import TermType


# noinspection PyPep8Naming
class bag3_digital__serNto1_fast(Module):
    """Module for library bag3_digital cell serNto1_fast.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'serNto1_fast.yaml')))

    def __init__(self, database: ModuleDB, params: Param, **kwargs: Any) -> None:
        Module.__init__(self, self.yaml_file, database, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        """Returns a dictionary from parameter names to descriptions.

        Returns
        -------
        param_info : Optional[Mapping[str, str]]
            dictionary from parameter names to descriptions.
        """
        return dict(
            ff_rst='Parameters for rst_flops',
            ff_set='Parameters for set_flop',
            rst_sync='Parameters for reset_sync',
            inv_d='Parameters for data inverter',
            inv_en='Parameters for enable inverters',
            ff='Parameters for flops',
            tinv='Parameters for tinvs',
            inv_clk='Parameters for clock inverter chain',
            inv_clk_div='Parameters for divided clock inverter chain',
            ratio='Number of serialized inputs/deserialized outputs',
            export_nets='True to export intermediate nets; False by default',
            is_rst_async='True if asynchronous rst input; False if synchronous rstb input. True by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(export_nets=False, is_rst_async=True)

    def get_master_basename(self) -> str:
        ratio: int = self.params['ratio']
        return f'ser_{ratio}to1'

    def design(self, ff_rst: Mapping[str, Any], ff_set: Mapping[str, Any], rst_sync: Mapping[str, Any],
               inv_d: Mapping[str, Any], inv_en: Mapping[str, Any], ff: Mapping[str, Any], tinv: Mapping[str, Any],
               inv_clk: Mapping[str, Any], inv_clk_div: Mapping[str, Any], ratio: int, export_nets: bool,
               is_rst_async: bool) -> None:
        """To be overridden by subclasses to design this module.

        This method should fill in values for all parameters in
        self.parameters.  To design instances of this module, you can
        call their design() method or any other ways you coded.

        To modify schematic structure, call:

        rename_pin()
        delete_instance()
        replace_instance_master()
        reconnect_instance_terminal()
        restore_instance()
        array_instance()
        """
        # reset sync
        if is_rst_async:
            self.instances['XRST_SYNC'].design(**rst_sync)
            self.reconnect_instance_terminal('XRST_SYNC', 'clkb', 'clk_buf')
        else:
            self.replace_instance_master('XRST_SYNC', 'bag3_digital', 'inv_chain', keep_connections=True)
            self.instances['XRST_SYNC'].design(**rst_sync)
            self.reconnect_instance('XRST_SYNC', [('in', 'rstb_sync_in'), ('outb', 'rst_sync'), ('out', 'rstb_sync')])
            self.rename_pin('rst', 'rstb_sync_in')

        # clock buffers
        self.instances['XINVD'].design(**inv_clk_div)
        self.instances['XINVC'].design(**inv_clk)

        # ff_set
        self.instances['XSET'].design(**ff_set)
        self.reconnect_instance('XSET', [('in', f'p<{ratio - 1}>'), ('clkb', 'clk_buf'), ('setb', 'rstb_sync')])

        # inv_en
        self.instances['XINV_P'].design(**inv_en)

        # ff_rst
        self.instances['XRST'].design(**ff_rst)
        rst_suf = f'<{ratio - 1}:1>'
        self.rename_instance('XRST', f'XRST{rst_suf}', [('in', f'p<{ratio - 2}:0>'), ('out', f'p{rst_suf}'),
                                                        ('clkb', 'clk_buf')])

        # ff - fast
        self.instances['XFF_F'].design(**ff)
        suf = f'<{ratio - 1}:0>'
        suf1 = f'<{ratio - 2}:0>'
        self.rename_instance('XFF_F', f'XFF_F{suf}', [('in', f'd{suf}'), ('out', f'd0{suf1},dout'),
                                                      ('clkb', 'clkb_buf')])

        # tinv - fast
        self.instances['XTINV_F'].design(**tinv)
        self.rename_instance('XTINV_F', f'XTINV_F{suf1}', [('in', f'd0{suf1}'), ('out', f't0{suf1}')])

        # current summer
        self.instances['XCS'].design(nin=2)
        cs_config = []
        for idx in range(ratio - 1):
            cs_config.insert(0, (f'XCS_{idx}', [('in<1:0>', f't1<{idx}>,t0<{idx}>'), ('out', f'db<{idx}>')]))
        self.array_instance('XCS', inst_term_list=cs_config)

        # data inverter
        self.instances['XINVT'].design(**inv_d)
        self.rename_instance('XINVT', f'XINVT{suf1}', [('in', f'db{suf1}'), ('out', f'd{suf1}')])

        # tinv - slow
        self.instances['XTINV_S'].design(**tinv)
        self.rename_instance('XTINV_S', f'XTINV_S{suf1}', [('in', f'd1{suf1}'), ('out', f't1{suf1}')])

        # ff - slow
        self.instances['XFF_S'].design(**ff)
        self.rename_instance('XFF_S', f'XFF_S{suf}', [('in', f'din{suf}'), ('out', f'd<{ratio - 1}>,d1{suf1}'),
                                                      ('clkb', 'clk_divb_buf')])
        self.rename_pin('din', f'din{suf}')

        if export_nets:
            for pin in (f'd{suf}', f'p{suf}', 'clk_buf', 'clkb_buf', 'clk_divb_buf', 'p0_buf',
                        'rst_sync'):
                self.add_pin(pin, TermType.output)
