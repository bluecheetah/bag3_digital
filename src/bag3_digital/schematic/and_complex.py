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

from typing import Mapping, Any, Sequence, Optional

import pkg_resources
from pathlib import Path

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param


# noinspection PyPep8Naming
class bag3_digital__and_complex(Module):
    """Module for library bag3_digital cell and_complex.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'and_complex.yaml')))

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
            nand_params_list='List of nand params',
            nor_params='nor params (or inv params for num_in < 4)',
            inv_params='Optional inv params',
            export_outb='True to export outb; True by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(inv_params=None, export_outb=True)

    def get_master_basename(self) -> str:
        num_in = 0
        nand_params_list: Sequence[Mapping[str, Any]] = self.params['nand_params_list']
        for _params in nand_params_list:
            num_in += _params.get('num_in', 2)
        return f'and{num_in}'

    def design(self, nand_params_list: Sequence[Mapping[str, Any]], nor_params: Mapping[str, Any],
               inv_params: Optional[Mapping[str, Any]], export_outb: bool) -> None:
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
        # nand design and reconnect
        num_in = 0
        nor_in = len(nand_params_list)
        nand_name_list = [f'XNAND{idx}' for idx in range(nor_in)]
        self.array_instance('XNAND', inst_name_list=nand_name_list)
        nand_out_list = []
        for idx, _nand_params in enumerate(nand_params_list):
            _name = f'XNAND{idx}'
            self.instances[_name].design(**_nand_params)
            _num_in = _nand_params.get('num_in', 2)
            _nand_out = f'nand_out{idx}'
            self.reconnect_instance(_name, [(f'in<{_num_in - 1}:0>', f'in<{num_in + _num_in - 1}:{num_in}>'),
                                            ('out', _nand_out)])
            nand_out_list.insert(0, _nand_out)
            num_in += _num_in
        if num_in > 2:
            self.rename_pin('in<1:0>', f'in<{num_in - 1}:0>')

        # nor design and reconnect
        if nor_in > 1:
            assert nor_in == nor_params.get('num_in', 2)
            self.instances['XNOR'].design(**nor_params)
            self.reconnect_instance_terminal('XNOR', f'in<{nor_in - 1}:0>', ','.join(nand_out_list))
        else:  # nor_in == 1
            self.replace_instance_master('XNOR', 'bag3_digital', 'inv', keep_connections=True)
            self.instances['XNOR'].design(**nor_params)
            self.reconnect_instance_terminal('XNOR', 'in', nand_out_list[0])

        # output inverter
        if export_outb:
            self.instances['XINV'].design(**inv_params)
        else:
            self.remove_instance('XINV')
            self.remove_pin('outb')
