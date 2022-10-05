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


# noinspection PyPep8Naming
class bag3_digital__cml_latch_res(Module):
    """Module for library bag3_digital cell cml_latch_res.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'cml_latch_res.yaml')))

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
            lch='channel length',
            seg_dict='transistor segments dictionary.',
            w_dict='transistor width dictionary.',
            th_dict='transistor threshold dictionary.',
            res_params='resistor width and length',
            has_rstb='True to add rstb functionality.',
            has_bridge='True to add bridge switch.',
            stack_br='Number of stacks in bridge switch.',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(has_rstb=False, has_bridge=False, stack_br=1)

    def design(self, lch: int, seg_dict: Mapping[str, int], w_dict: Mapping[str, int],
               th_dict: Mapping[str, str], res_params: Mapping[str, int],
               has_rstb: bool, has_bridge: bool, stack_br: int) -> None:

        for name in ['XRP', 'XRN']:
            self.design_resistor(name, res_params)

        for name in ['in', 'clk', 'tail', 'fb']:
            uname = name.upper()
            w = w_dict[name]
            nf = seg_dict[name]
            intent = th_dict[name]
            if name == 'tail':
                inst_name = 'XTAIL'

                if has_rstb:
                    self.instances[inst_name].design(lch=lch, w=w, seg=nf, intent=intent, stack=2)
                else:
                    self.instances[inst_name].design(lch=lch, w=w, seg=nf, intent=intent, stack=1)
                    self.reconnect_instance_terminal(inst_name, 'g', 'vbias')
            elif name == 'clk':
                self.design_transistor(f'X{uname}', w, lch, nf, intent)
                self.design_transistor(f'X{uname}B', w, lch, nf, intent)
            else:
                self.design_transistor(f'X{uname}P', w, lch, nf, intent)
                self.design_transistor(f'X{uname}N', w, lch, nf, intent)

        # design biases
        for name in ['in', 'clk', 'tail']:
            uname = name.upper()
            w = w_dict[name]
            nf = seg_dict[name]
            intent = th_dict[name]
            if name == 'tail':
                inst_name = 'XB_TAIL'

                if has_rstb:
                    self.instances[inst_name].design(lch=lch, w=w, seg=nf, intent=intent, stack=2)
                else:
                    self.instances[inst_name].design(lch=lch, w=w, seg=nf, intent=intent, stack=1)
                    self.reconnect_instance_terminal(inst_name, 'g', 'vbias')
            elif name == 'in':
                self.design_transistor(f'XB_{uname}', w, lch, nf*2, intent)
            else:
                self.design_transistor(f'XB_{uname}', w, lch, nf, intent)

        if has_bridge:
            w = w_dict['br']
            seg = seg_dict['br']
            intent = th_dict['br']
            self.instances['XBR'].design(lch=lch, w=w, seg=seg, intent=intent, stack=stack_br)
            if stack_br == 1:
                self.reconnect_instance_terminal('XBR', 'g', 'clk')
            else:
                self.reconnect_instance_terminal('XBR', f'g<{stack_br - 1}:0>', 'clk')
        else:
            self.remove_instance('XBR')

        if not has_rstb:
            self.remove_pin('rstb')
