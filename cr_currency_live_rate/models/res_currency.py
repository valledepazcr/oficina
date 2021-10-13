
from odoo import models, fields, api, _
from zeep import Client
import xml.etree.ElementTree as et
import datetime

from odoo.exceptions import UserError, ValidationError

import logging

_logger = logging.getLogger(__name__)


class xResCurrency(models.Model):
    _inherit = 'res.currency'

    rate = fields.Float(digits='Currency Rate Precision')


class xResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    # Aumenta la precisión para que el factor de cambio de $us a Colon tenga suficientes decimales (1 / TC venta)
    rate = fields.Float(string='Factor TC Venta', digits='Currency Rate Precision', )

    x_rate2 = fields.Float(string='Factor TC Compra', digits='Currency Rate Precision',
                          help='Tipo de Cambio de Compra')

    x_cr_rate_selling = fields.Float(string='Tipo Cambio Venta', digits=(16, 4),
                                    help='Tipo de cambio de venta')
    x_cr_rate_buying = fields.Float(string='Tipo Cambio Compra', digits=(16, 4),
                                    help='Tipo de cambio de Compra')

    @api.onchange('x_cr_rate_selling')
    def _onchange_x_cr_rate_selling(self):
        # conversion de colones       
        if self.currency_id.name in ('USD', 'EUR') and self.x_cr_rate_selling > 0:
            rate = None if not self.x_cr_rate_selling else 1 / self.x_cr_rate_selling
            if self.company_id and self.company_id.currency_id != self.currency_id:
                self.rate = rate
            elif not self.company_id and self.env.company.currency_id != self.currency_id:
                self.rate = rate

    @api.onchange('x_cr_rate_buying')
    def _onchange_x_cr_rate_buying(self):
        if self.currency_id.name in ('USD', 'EUR') and self.x_cr_rate_buying > 0:
            rate = None if not self.x_cr_rate_buying else 1 / self.x_cr_rate_buying
            if self.company_id and self.company_id.currency_id != self.currency_id:
                self.x_rate2 = rate
            elif not self.company_id and self.env.company.currency_id != self.currency_id:
                self.x_rate2 = rate


    @api.model
    def cron_cr_get_currency_rate(self, dias_atras=2):
        # _logger.debug(">> cron_cr_get_rate_bcr:  Obteniendo el tipo de cambio from BCCR")

        exchange_source = self.env['ir.config_parameter'].sudo().get_param('x_exchange_source')
        bccr_username = self.env['ir.config_parameter'].sudo().get_param('x_bccr_username')
        bccr_email = self.env['ir.config_parameter'].sudo().get_param('x_bccr_email')
        bccr_token = self.env['ir.config_parameter'].sudo().get_param('x_bccr_token')

        if not( bccr_username and bccr_email and bccr_token) or exchange_source != 'bccr':
            return

        fhasta = datetime.datetime.now().date() # hasta hoy        
        fdesde = datetime.datetime.now().date() - datetime.timedelta(days=abs(dias_atras)) 
        initial_date = fdesde.strftime('%d/%m/%Y')
        end_date = fhasta.strftime('%d/%m/%Y') 
    
        #
        url_exchange = 'https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx?WSDL'
        client = Client(url_exchange)

        _logger.info(">> cron_cr_get_rate_bcr: Obteniendo Tipos de Cambio del %s  al %s", initial_date, end_date)

        # crea funcion Lambda
        ObtenerIndicadorEconomico = lambda i : client.service.ObtenerIndicadoresEconomicosXML(Indicador = i,
                                                                FechaInicio=initial_date,
                                                                FechaFinal=end_date,
                                                                Nombre=bccr_username,
                                                                SubNiveles='N',
                                                                CorreoElectronico=bccr_email,
                                                                Token=bccr_token )

        currency_CRC_id = self.env['res.currency'].search([('name', '=', 'CRC')]).id
        currency_USD_id = self.env['res.currency'].search([('name', '=', 'USD')]).id
        currency_EUR = self.env['res.currency'].search([('name', '=', 'EUR')])
        
        sellingRateNodes = buyingRateNodes = euroRateNodes = ""
        try:
            # tipo de cambio de Venta (dolar-Colón)
            response = ObtenerIndicadorEconomico('318')            
            xmlResponse = et.fromstring(response)            
            sellingRateNodes = xmlResponse.findall("./INGC011_CAT_INDICADORECONOMIC")

            # tipo de cambio de Compra (dolar-Colón)
            response = ObtenerIndicadorEconomico('317')
            xmlResponse = et.fromstring(response)
            buyingRateNodes = xmlResponse.findall("./INGC011_CAT_INDICADORECONOMIC")

            # tipo de cambio de Compra (euro-dolar)
            if currency_EUR.active:
                response = ObtenerIndicadorEconomico('333')
                xmlResponse = et.fromstring(response)
                euroRateNodes = xmlResponse.findall("./INGC011_CAT_INDICADORECONOMIC")
        except Exception as error:
            _logger.error(">> cron_cr_get_rate_bcr: Exception obteniendo indicadores de tipos de cambio del  BCCR. Error: %s", error )


        if len(sellingRateNodes) > 0 and len(sellingRateNodes) == len(buyingRateNodes):
            #--------------------
            # Registra el tipo de cambio para compañías en moneda COLONES
            # _logger.info(">> cron_cr_get_rate_bcr: Registra tipos de Cambio General para Compañías en Colones" )
            nodeIndex = 0
            lenEuros = len(euroRateNodes)
            while nodeIndex < len(sellingRateNodes):
                # _logger.info(">> cron_cr_get_rate_bcr: nodoIndex %s / %s", nodeIndex, len(sellingRateNodes))
                if self.get_xml_data(sellingRateNodes, nodeIndex, "DES_FECHA") == self.get_xml_data(buyingRateNodes, nodeIndex, "DES_FECHA"):
                    # _logger.info(">> cron_cr_get_rate_bcr: des_fecha selling (%s)", self.get_xml_data(sellingRateNodes, nodeIndex,"DES_FECHA") ) 
                    currentDateStr = datetime.datetime.strptime(self.get_xml_data(sellingRateNodes, nodeIndex, "DES_FECHA"), "%Y-%m-%dT%H:%M:%S-06:00").strftime('%Y-%m-%d')

                    # tipos de Cambio en Colones  según el BCCR
                    sellingOriginalRate = self.get_xml_data(sellingRateNodes, nodeIndex, "NUM_VALOR")
                    buyingOriginalRate = self.get_xml_data(buyingRateNodes, nodeIndex, "NUM_VALOR")

                    if sellingOriginalRate and buyingOriginalRate:
                        # La moneda de companía es COLONES, y odoo registra la conversiones a dólares con un factor 1 entre tipo de cambio
                        sellingRate = 1 / sellingOriginalRate
                        buyingRate = 1 / buyingOriginalRate

                        # _logger.info(">> cron_cr_get_rate_bcr: Tipo Cambio a Insertar: Venta %s  Compra", sellingRate, buyingRate )
                        self.procesa_tipo_cambio(None, currency_USD_id, currentDateStr, sellingRate, buyingRate, sellingOriginalRate, buyingOriginalRate)

                        # Tipos de Cambio del Euro respecto al Colón
                        # _logger.info(">> cron_cr_get_rate_bcr cia en COLONES: revisa Euros" )
                        if nodeIndex < lenEuros and self.get_xml_data(sellingRateNodes, nodeIndex, "DES_FECHA") == self.get_xml_data(euroRateNodes, nodeIndex, "DES_FECHA"):
                            euroOriginalRate = self.get_xml_data(euroRateNodes, nodeIndex, "NUM_VALOR") 
                            # _logger.info(">> cron_cr_get_rate_bcr cia en COLONES: revisa Euros:  %s ", euroOriginalRate)
                            if euroOriginalRate:
                                sellingOriginalRate = (sellingOriginalRate * euroOriginalRate)
                                buyingOriginalRate = (buyingOriginalRate * euroOriginalRate)
                                sellingRate = 1 / sellingOriginalRate
                                buyingRate = 1 / buyingOriginalRate
                                self.procesa_tipo_cambio(None, currency_EUR.id, currentDateStr, sellingRate, buyingRate, sellingOriginalRate, buyingOriginalRate)
                else:
                    _logger.info(">> cron_cr_get_rate_bcr: Error on date exchange rates of buying (%s) and selling (%s)" 
                                  ,self.get_xml_data(buyingRateNodes,nodeIndex,"DES_FECHA"), self.get_xml_data(sellingRateNodes, nodeIndex,"DES_FECHA"))
                nodeIndex += 1

            #--------------------
            # Registra el tipo de cambio para compañías en moneda DOLARES (solo si existen)
            companies = self.env['res.company'].search([('currency_id','=', currency_USD_id)]) 
            for company in companies:
                # _logger.info(">> cron_cr_get_rate_bcr: Carga tipo de Cambio a Compañía: %s", company.name[:30] )
                nodeIndex = 0
                while nodeIndex < len(sellingRateNodes):
                    if self.get_xml_data(sellingRateNodes, nodeIndex, "DES_FECHA") == self.get_xml_data(buyingRateNodes, nodeIndex, "DES_FECHA"):
                        currentDateStr = datetime.datetime.strptime(self.get_xml_data(sellingRateNodes, nodeIndex,"DES_FECHA"), "%Y-%m-%dT%H:%M:%S-06:00").strftime('%Y-%m-%d')

                        # tipos de Cambio en Colones  según el BCCR
                        sellingOriginalRate = self.get_xml_data(sellingRateNodes, nodeIndex, "NUM_VALOR") 
                        buyingOriginalRate = self.get_xml_data(buyingRateNodes, nodeIndex, "NUM_VALOR") 

                        # La moneda de companía es DOLARES, se usa el tipo de cambio traido del BCCR
                        sellingRate = sellingOriginalRate
                        buyingRate = buyingOriginalRate

                        # _logger.info(">> cron_cr_get_rate_bcr: Tipo Cambio a Insertar: Venta %s  Compra", sellingRate, buyingRate )
                        self.procesa_tipo_cambio(company.id, currency_CRC_id, currentDateStr, sellingRate, buyingRate, sellingOriginalRate, buyingOriginalRate)

                        # Tipos de Cambio del Euro respecto al Dolar (dolar es monea debil)
                        if nodeIndex < lenEuros and self.get_xml_data(sellingRateNodes, nodeIndex, "DES_FECHA") == self.get_xml_data(euroRateNodes,nodeIndex,"DES_FECHA"):
                            currentDateStr = datetime.datetime.strptime(self.get_xml_data(sellingRateNodes, nodeIndex,"DES_FECHA"), "%Y-%m-%dT%H:%M:%S-06:00").strftime('%Y-%m-%d')
                            euroOriginalRate = self.get_xml_data(euroRateNodes, nodeIndex, "NUM_VALOR")
                            if euroOriginalRate:
                                sellingOriginalRate = euroOriginalRate
                                buyingOriginalRate = euroOriginalRate
                                sellingRate = 1 / sellingOriginalRate
                                buyingRate = 1 / buyingOriginalRate
                                self.procesa_tipo_cambio(company.id, currency_EUR.id, currentDateStr, sellingRate, buyingRate, sellingOriginalRate, buyingOriginalRate)                        

                    nodeIndex += 1
        else:
            _logger.error(">> cron_cr_get_rate_bcr: La cantidad de tipos tipos de cambio de venta es diferente a la cantidad de compra, para las fechas del %s  al   %s", initial_date, end_date )


    def get_xml_data(self, xml_data, node_ind, node_tag):
        xelem = xml_data[node_ind].find(node_tag)
        if et.iselement(xelem):
            if node_tag == "NUM_VALOR":
                return float( xelem.text )
            else:
                return xelem.text
        else:
            return None

    def procesa_tipo_cambio(self, companyid, currencyid, currStrDate, rate, rate2, sellingRate, buyingRate):        
        rate_id = self.env['res.currency.rate'].search([('currency_id','=',currencyid),('company_id','=',companyid),('name', '=', currStrDate)], limit=1)
        if not rate_id:
            newRate = self.create({'company_id': companyid,
                                    'currency_id': currencyid,
                                    'name': currStrDate,
                                    'rate': rate,
                                    'x_rate2': rate2,
                                    'x_cr_rate_selling': sellingRate,
                                    'x_cr_rate_buying': buyingRate,
                                  } )        
