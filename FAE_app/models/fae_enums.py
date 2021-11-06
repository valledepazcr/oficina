from enum import Enum

policy_id = 'https://www.hacienda.go.cr/ATV/ComprobanteElectronico/docs/esquemas/2016/v4.2/ResolucionComprobantesElectronicosDGT-R-48-2016_4.2.pdf'

# index by "tipo_connect"
dgt_url_token = {
  'api-stag' : 'https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token',
  'api-prod' : 'https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token',
}

dgt_url = {
  'api-stag' : 'https://api.comprobanteselectronicos.go.cr/recepcion-sandbox/v1/recepcion/',
  'api-prod' : 'https://api.comprobanteselectronicos.go.cr/recepcion/v1/recepcion/',
  'api-ae'   : 'https://api.hacienda.go.cr/fe/ae?identificacion=', 
  'api-ex'   : 'https://api.hacienda.go.cr/fe/ex?autorizacion=',
}


tipo_doc_name = {
  'FE':  'FacturaElectronica',
  'ND':  'NotaDebitoElectronica',
  'NC':  'NotaCreditoElectronica',
  'TE':  'TiqueteElectronico',
  'FEC': 'FacturaElectronicaCompra',
  'FEE': 'FacturaElectronicaExportacion',
}


tipo_doc_num = {
    'FE' : '01',
    'ND' : '02',
    'NC' : '03',
    'TE' : '04',
    'FEC' : '08',
    'FEE' : '09',
    'A' : '05',
    'P' : '06',
    'R' : '07',
}

num_tipo_doc = {'01': 'FE', '02': 'ND', '03': 'NC', '04': 'TE', '09': 'FEE'}


xmlns_hacienda = {
  'FE':  'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/facturaElectronica',
  'ND':  'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/notaDebitoElectronica',
  'NC':  'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/notaCreditoElectronica',
  'TE':  'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/tiqueteElectronico',
  'FEC': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/facturaElectronicaCompra',
  'FEE': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/facturaElectronicaExportacion',
  'MR':  'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/mensajeReceptor',
}

schema_location = {
  'FE':  'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/facturaElectronica.xsd',
  'ND':  'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/NotaDebitoElectronica_V4.3.xsd',
  'NC':  'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/NotaCreditoElectronica_V4.3.xsd',
  'TE':  'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/TiqueteElectronico_V4.3.xsd',
  'FEC': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/FacturaElectronicaCompra_V4.3.xsd',
  'FEE': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/FacturaElectronicaExportacion_V4.3.xsd',
  'MR':  'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/mensajeReceptor.xsd'
}


situacion_comprobante = {
  '1' : 'Normal',  
  '2' : 'Contingencia',
  '3' : 'Sin Internet',
}
