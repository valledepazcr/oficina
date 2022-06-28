##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging
from datetime import datetime
from dateutil import relativedelta


from odoo import models, fields, api, _
from odoo.exceptions import UserError

from xlrd import open_workbook, XL_CELL_EMPTY, XL_CELL_BLANK, XL_CELL_TEXT

import base64
import re
from calendar import monthrange

_logger = logging.getLogger(__name__)


class hr_payslip_load_inputs(models.TransientModel):
    _name = "hr.payslip.load.inputs"
    _description = "Generate payslips from a inputs file"

    input_file = fields.Binary("Test Importing File", required=True)
    previous_payroll_date = fields.Date("Last Payroll Date")
    from_column = fields.Integer("From Column")
    to_column = fields.Integer("To Column")
    run_days = fields.Integer("Run Days", default=15)
    append_inputs = fields.Boolean(
            "Append Inputs",
            help="If it is checked, no payslip will be generated and inputs will be added to existing ones.",
        )
    off_cycle_new_hires = fields.Boolean(
            "Off Cycle New Hires ?",
            help="If it is checked, will only load base salary for new hires starting from Last Payroll Date",
        )
    overwrite_payslip_run_id = fields.Many2one(
            "hr.payslip.run", "Overwrite previous Payslip Batches"
        )

    def sheet_to_dict(
        self, sheet, from_column, to_column
    ):
        headers = []
        result = {}
        _logger.error("Colums: %s  Rows: %s", sheet.ncols, sheet.nrows)

        for col in range(sheet.ncols):
            headers.append(sheet.cell(1, col).value)

        for row in range(2, sheet.nrows):
            line = []
            emp_id = sheet.cell(row, 0).value
            for col in range(from_column, to_column + 1):
                if sheet.cell(row, col).ctype in (
                    XL_CELL_BLANK,
                    XL_CELL_EMPTY,
                ):
                    continue
                elif sheet.cell(row, col).ctype == XL_CELL_TEXT:
                    line.append(
                        (
                            headers[col],
                            re.sub(
                                "[a-zA-Z, \xa2]",
                                "",
                                sheet.cell(row, col).value,
                            ),
                        )
                    )
                else:
                    line.append((headers[col], sheet.cell(row, col).value))
            result[emp_id] = line
            _logger.error("Employee: %s Line : %s ", emp_id, line)

        return result

    def create_payslips(
        self,
        payroll_dict,
        previous_payroll_date,
        off_cycle_new_hires,
        run_days,
        previous_payslip_run_id,
    ):
        slip_pool = self.env["hr.payslip"]
        run_pool = self.env["hr.payslip.run"]
        contract_obj = self.env["hr.contract"]

        active_id = self.env.context['active_id']
        run_data = run_pool.browse(active_id)
        from_date = run_data.date_start
        to_date = run_data.date_end
        credit_note = run_data.credit_note
        journal_id = run_data.journal_id.id

        slip_ids = []

        search_criteria = [
            "|",
            ("date_end", "=", False),
            ("date_end", ">=", from_date),
        ]
        if off_cycle_new_hires:
            search_criteria = [
                "&",
                ("date_start", ">", previous_payroll_date),
            ] + search_criteria

        _logger.error("MAB *** search_criteria = %s", search_criteria)
        contract_datas = contract_obj.search(search_criteria)
        _logger.error("MAB *** contract_datas = %s", contract_datas)

        for contract_data in contract_datas:
            _logger.error("MAB *** contract_data id = %s", contract_data.id)
            if contract_data.date_end:
                # The employee was terminated, so we need to check for real days worked
                base_days = (
                    run_days
                    - min(30, to_date.day)  #min(30, int(to_date[8:]))
                    + min(contract_data.date_end.day, 30) #min(int(contract_data.date_end[8:]), 30)
                )
            else:
                base_days = run_days

            contract_start_date = contract_data.date_start
            if previous_payroll_date < contract_start_date:
                payroll_month = from_date.month
                contract_start_month = contract_start_date.month

                delta_days = relativedelta.relativedelta(
                    from_date, contract_start_date
                )
                month_adjustment = 0
                if payroll_month > contract_start_month:
                    if contract_start_month in (1, 3, 5, 7, 8, 10, 12):
                        month_adjustment = -1
                    elif contract_start_month == 2:
                        month_adjustment = 2
                base_days += delta_days.days + month_adjustment
            base_hours = base_days * 8 #contract_data.hourly_wage

            emp_inputs = [
                {
                    "name": "CREHB01",
                    "code": "CREHB01",
                    "amount": base_hours,
                    "contract_id": contract_data.id,
                }
            ]

            if not off_cycle_new_hires:
                inputs = payroll_dict.get(
                    contract_data.employee_id.identification_id, []
                )
                for input_code, input_value in inputs:
                    input_rec = {
                        "name": input_code,
                        "code": input_code,
                        "amount": input_value,
                        "contract_id": contract_data.id,
                    }
                    emp_inputs.append(input_rec)
            if contract_data.employee_id.identification_id:
                contract_identification = contract_data.employee_id.identification_id
            else:
                contract_identification = " "

            _logger.error("MAB *** ID = %s", contract_data.employee_id.id)
            _logger.error("MAB *** Emp ID = %s", contract_identification)
            _logger.error("MAB *** Emp name = %s", contract_data.employee_id.name)
            #_logger.error("MAB *** Emp last_name = %s", contract_data.employee_id.last_name)
            _logger.error("MAB *** Emp ID = %s", contract_data.struct_id.id)
            _logger.error("MAB *** struct_id = %s", contract_data.id)
            _logger.error("MAB *** active_id = %s", active_id)

            slip_data = {
                "employee_id": contract_data.employee_id.id,
                "name": contract_identification
                + " payslip details for "
                + contract_data.employee_id.name,
                #+ " "
                #+ contract_data.employee_id.last_name,
                "struct_id": contract_data.struct_id.id,
                "contract_id": contract_data.id or False,
                "payslip_run_id": active_id,
                "input_line_ids": [(0, 0, x) for x in emp_inputs],
                "date_from": from_date,
                "date_to": to_date,
                "credit_note": credit_note,
                "journal_id": journal_id,
            }
            slip_ids.append(
                slip_pool.create(slip_data)
            )

        _logger.error("MAB *** slip_ids = %s", slip_ids)
        #slip_pool.compute_sheet(slip_ids)
        for slip in slip_ids:
            slip.compute_sheet()
        return slip_ids

    def add_inputs(
        self,
        payroll_dict,
        overwrite_payslip_run_id,
    ):
        slip_pool = self.env["hr.payslip"]
        slip_input_pool = self.env["hr.payslip.input"]
        emp_pool = self.env["hr.employee"]

        active_id = self.env.context['active_id']

        slip_ids = []
        for emp_code, inputs in payroll_dict.items():
            if not inputs:
                continue

            emp_id = emp_pool.search([("identification_id", "=", emp_code)])
            slip_id = slip_pool.search(
                [
                    (
                        "payslip_run_id",
                        "=",
                        overwrite_payslip_run_id or active_id,
                    ),
                    ("employee_id", "=", emp_id.id),
                ],
            )
            if slip_id:
                if isinstance(slip_id, list):
                    if len(slip_id):
                        slip_id = slip_id[0]
                    else:
                        continue  # should raise error
            else:
                run_pool = self.env["hr.payslip.run"]
                run_data = {}
                run_data = run_pool.browse( [active_id])
                from_date = run_data.date_start
                to_date = run_data.date_end
                credit_note = run_data.credit_note
                journal_id = run_data.journal_id
                contract_obj = self.env["hr.contract"]
                contract_data = contract_obj.search([("name", "=", emp_code)])[0]
                _logger.error("MAB *** Emp Code = %s", emp_code)

                if contract_data.employee_id.identification_id:
                    contract_identification = contract_data.employee_id.identification_id
                else:
                    contract_identification = " "
                slip_data = {
                    "employee_id": contract_data.employee_id.id,
                    "name": contract_identification
                    + " payslip details for "
                    + contract_data.employee_id.name,
                    #+ " "
                    #+ contract_data.employee_id.last_name,
                    "struct_id": contract_data.struct_id.id,
                    "contract_id": contract_data.id or False,
                    "payslip_run_id": active_id,
                    "date_from": from_date,
                    "date_to": to_date,
                    "credit_note": credit_note,
                    "journal_id": journal_id,
                }
                slip_id = slip_pool.create(slip_data)

            slip_contract_id = contract_data.id

            if overwrite_payslip_run_id:
                slip_pool.write(
                    slip_id,
                    {"payslip_run_id": active_id},
                )

            for input_code, input_value in inputs:
                current_input = slip_input_pool.search([("payslip_id", "=", slip_id), ("code", "=", input_code)],)
                if isinstance(current_input, list):
                    if len(current_input):
                        current_input = current_input[0]
                    else:
                        current_input = False

                if current_input:
                    input_obj = slip_input_pool.browse(cr, uid, current_input,)
                    slip_input_pool.write(
                        current_input,
                        {"amount": input_obj.amount + float(input_value)},
                        context=context,
                    )
                else:
                    input_rec = {
                        "name": input_code,
                        "code": input_code,
                        "amount": input_value,
                        "contract_id": slip_contract_id,
                        "payslip_id": slip_id,
                    }
                    slip_input_pool.create(input_rec)
                slip_ids.append(slip_id)
            # need to implement automatic get old value to get difference...
            # current_slip_net_id = slip_line_pool.search(cr, uid, [('payslip_id', '=', slip_id),('code', '=', 'NETCR')])
            # current_slip_net =
        #slip_pool.compute_sheet(slip_ids)
        for slip in slip_ids:
            slip.compute_sheet()
        return slip_ids

    def load_inputs(self):
        input_file = self.input_file
        from_column = self.from_column
        to_column = self.to_column
        run_days = self.run_days
        append_inputs = self.append_inputs
        off_cycle_new_hires = self.off_cycle_new_hires
        overwrite_payslip_run_id = (
            self.overwrite_payslip_run_id
            and self.overwrite_payslip_run_id[0]
        )
        previous_payroll_date = self.previous_payroll_date
        if not off_cycle_new_hires:
            if not input_file:
                raise UserError(
                    _("You must select a file to generate payslip(s)."),
                )

            base64content = base64.b64decode(input_file)
            workbook = open_workbook(file_contents=base64content)
            sheet = workbook.sheets()[0]

            payroll_dict = self.sheet_to_dict(
                sheet, from_column, to_column
            )

            if not payroll_dict:
                raise UserError(
                    _("No data loaded, please check file name and content"),
                )
        else:
            payroll_dict = {}

        if not append_inputs:
            slip_ids = self.create_payslips(
                payroll_dict,
                previous_payroll_date,
                off_cycle_new_hires,
                run_days,
                overwrite_payslip_run_id,
            )
        else:
            slip_ids = self.add_inputs(payroll_dict, overwrite_payslip_run_id,)

        #return {"type": "ir.actions.act_window_close"}


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
