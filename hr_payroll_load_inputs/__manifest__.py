# -*- encoding: utf-8 -*-
############################################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>). All Rights Reserved
#    Copyright (C) 2008-2009 AJM Technologies S.A. (<http://www.ajm.lu>). All Rights Reserved
#    Copyright (c) 2010-2011 Zikzakmedia S.L. (http://zikzakmedia.com) All Rights Reserved.
#                       Jesús Martín <jmartin@zikzakmedia.com>
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
############################################################################################

{
    "name": "hr_payroll_load_inputs",
    "version": "14.0.1.0.0",
    "author": "CYS Futuro",
    "website": "http://www.cysfuturo.com",
    "license": "GPL-3",
    "category": "Human Resources",
    "description": """
This module enables creating payslips from inputs on csv or excel files.
""",
    "depends": [
        "hr_payroll_community",
    ],
    "init_xml": [],
    "demo_xml": [],
    "data": [
        "wizard/hr_payroll_load_payslips_from_inputs.xml",
        'security/ir.model.access.csv',
        ###'hr_payroll_load_inputs_report.xml',
    ],
    "active": False,
    "installable": True,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
