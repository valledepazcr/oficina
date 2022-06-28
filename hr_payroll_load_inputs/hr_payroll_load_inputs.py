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

import time
from datetime import datetime, date
from dateutil import relativedelta

from odoo import tools
from odoo.osv import fields, osv
from odoo.tools.translate import _


class hr_employee(osv.osv):
    """
    Employee
    """

    _inherit = "hr.employee"
    _description = "Employee"

    def avg_day_salary(self, from_date, to_date=None):
        start_date = date.strptime(from_date, "%Y-%m-%d") - relativedelta(
            months=6
        )
        if to_date is None:
            to_date = datetime.now().strftime("%Y-%m-%d")
        end_date = date.strptime(to_date, "%Y-%m-%d") - relativedelta(months=6)

        code = "CRGROSS"

        self.cr.execute(
            "SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)\
                    FROM hr_payslip as hp, hr_payslip_line as pl \
                    WHERE hp.employee_id = %s AND hp.state = 'done' \
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s",
            (
                self.id,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
                code,
            ),
        )
        res = self.cr.fetchone()
        return res and res[0] or 0.0


class hr_payslip_worked_days(osv.osv):
    """
    Payslip Worked Days
    """

    _name = "hr.payslip.worked_days"
    _description = "Payslip Worked Days"
    _inherit = "hr.payslip.worked_days"
    _columns = {
        "number_of_extra_hours": fields.float("Number of Extra Hours"),
    }


hr_payslip_worked_days()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
