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
class bag3_digital__inv_diff(Module):
    """Module for library bag3_digital cell inv_diff.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'inv_diff.yaml')))

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
            inv_in='Parameters for input tristate inverters',
            inv_fb='Parameters for keeper tristate inverters',
            dummy_dev='True if adding dummy bordering devices',
            dummy_params='Parameters for dummy devices',
        )

    def design(self, inv_in: Mapping[str, Any], inv_fb: Mapping[str, Any],
               dummy_dev: bool, dummy_params: Mapping[str, Any]) -> None:
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
        # input inverters
        self.reconnect_instance('XIN', [('pout', 'midb<0>'), ('nout', 'midb<0>')])
        self.reconnect_instance('XINB', [('pout', 'mid<0>'), ('nout', 'mid<0>')])
        self.instances['XIN'].design(**inv_in)
        self.instances['XINB'].design(**inv_in)

        # feedback inverters
        self.reconnect_instance('XFB0', [('pout', 'midb<1>'), ('nout', 'midb<1>')])
        self.reconnect_instance('XFB1', [('pout', 'mid<1>'), ('nout', 'mid<1>')])
        self.instances['XFB0'].design(**inv_fb)
        self.instances['XFB1'].design(**inv_fb)

        # current summers
        self.instances['XCS0'].design(nin=2)
        self.instances['XCS1'].design(nin=2)

        # dummies
        if dummy_dev:
            pdummy_params = dummy_params.to_dict()
            ndummy_params = dummy_params.to_dict()
            pdummy_params.pop('wn')
            pdummy_params['w'] = pdummy_params.pop('wp')
            ndummy_params.pop('wp')
            ndummy_params['w'] = ndummy_params.pop('wn')
            self.design_transistor('XNDUMM0', **ndummy_params)
            self.design_transistor('XNDUMM1', **ndummy_params)
            self.design_transistor('XNDUMM2', **ndummy_params)
            self.design_transistor('XNDUMM3', **ndummy_params)
            self.design_transistor('XPDUMM0', **pdummy_params)
            self.design_transistor('XPDUMM1', **pdummy_params)
            self.design_transistor('XPDUMM2', **pdummy_params)
            self.design_transistor('XPDUMM3', **pdummy_params)
        else:
            self.remove_instance('XNDUMM0')
            self.remove_instance('XNDUMM1')
            self.remove_instance('XNDUMM1')
            self.remove_instance('XNDUMM1')
            self.remove_instance('XPDUMM0')
            self.remove_instance('XPDUMM1')
            self.remove_instance('XPDUMM1')
            self.remove_instance('XPDUMM1')
