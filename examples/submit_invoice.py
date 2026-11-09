"""Minimal JoFotara submission example (MIT).

Builds a tiny UBL 2.1 invoice, base64-encodes it and POSTs it. It is a *teaching* example:
a real integration must fill every element your registration requires and follow the current
official specification. Run it in dry-run mode first (default) to see the payload without
calling the API:

    python submit_invoice.py                    # dry run, prints the XML + request
    JOFOTARA_CLIENT_ID=... JOFOTARA_SECRET_KEY=... python submit_invoice.py --send
"""
import base64
import json
import os
import sys
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from xml.sax.saxutils import escape

import requests

URL = "https://backend.jofotara.gov.jo/core/invoices/"
INVOICE_TYPES = {  # (category) -> {payment kind -> InvoiceTypeCode/@name}
    "income": {"cash": "011", "receivable": "021"},
    "general_sales": {"cash": "012", "receivable": "022"},
    "special_sales": {"cash": "013", "receivable": "023"},
}


def amt(x) -> str:
    return str(Decimal(x).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def build_xml(*, number, icv, tin, seller, income_source, lines, tax_rate="16",
              category="general_sales", cash=True, credit=False, invoice_uuid=None):
    """lines = [(name, qty, unit_price_excluding_tax)]"""
    invoice_uuid = invoice_uuid or str(uuid.uuid4())      # generate ONCE, store, reuse on retry
    rate = Decimal(tax_rate)
    net = sum(Decimal(q) * Decimal(p) for _, q, p in lines)
    tax = (net * rate / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    grand = net + tax
    type_name = INVOICE_TYPES[category]["cash" if cash else "receivable"]
    body = []
    for i, (name, q, p) in enumerate(lines, 1):
        line_net = Decimal(q) * Decimal(p)
        line_tax = (line_net * rate / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        body.append(f"""  <cac:InvoiceLine>
    <cbc:ID>{i}</cbc:ID>
    <cbc:InvoicedQuantity unitCode="PCE">{q}</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="JOD">{amt(line_net)}</cbc:LineExtensionAmount>
    <cac:TaxTotal>
      <cbc:TaxAmount currencyID="JOD">{amt(line_tax)}</cbc:TaxAmount>
      <cbc:RoundingAmount currencyID="JOD">{amt(line_net + line_tax)}</cbc:RoundingAmount>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="JOD">{amt(line_net)}</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="JOD">{amt(line_tax)}</cbc:TaxAmount>
        <cac:TaxCategory>
          <cbc:ID schemeAgencyID="6" schemeID="UN/ECE 5305">S</cbc:ID>
          <cbc:Percent>{amt(rate)}</cbc:Percent>
          <cac:TaxScheme><cbc:ID schemeAgencyID="6" schemeID="UN/ECE 5153">VAT</cbc:ID></cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item><cbc:Name>{escape(name)}</cbc:Name></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="JOD">{amt(p)}</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ProfileID>reporting:1.0</cbc:ProfileID>
  <cbc:ID>{escape(number)}</cbc:ID>
  <cbc:UUID>{invoice_uuid}</cbc:UUID>
  <cbc:IssueDate>{date.today().isoformat()}</cbc:IssueDate>
  <cbc:InvoiceTypeCode name="{type_name}">{'381' if credit else '388'}</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>JOD</cbc:DocumentCurrencyCode>
  <cbc:TaxCurrencyCode>JOD</cbc:TaxCurrencyCode>
  <cac:AdditionalDocumentReference><cbc:ID>ICV</cbc:ID><cbc:UUID>{icv}</cbc:UUID></cac:AdditionalDocumentReference>
  <cac:AccountingSupplierParty><cac:Party>
    <cac:PostalAddress><cac:Country><cbc:IdentificationCode>JO</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
    <cac:PartyTaxScheme><cbc:CompanyID>{escape(tin)}</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
    <cac:PartyLegalEntity><cbc:RegistrationName>{escape(seller)}</cbc:RegistrationName></cac:PartyLegalEntity>
  </cac:Party></cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty><cac:Party>
    <cac:PostalAddress><cac:Country><cbc:IdentificationCode>JO</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
    <cac:PartyLegalEntity><cbc:RegistrationName></cbc:RegistrationName></cac:PartyLegalEntity>
  </cac:Party></cac:AccountingCustomerParty>
  <cac:SellerSupplierParty><cac:Party><cac:PartyIdentification><cbc:ID>{escape(income_source)}</cbc:ID></cac:PartyIdentification></cac:Party></cac:SellerSupplierParty>
  <cac:AllowanceCharge><cbc:ChargeIndicator>false</cbc:ChargeIndicator><cbc:AllowanceChargeReason>discount</cbc:AllowanceChargeReason><cbc:Amount currencyID="JOD">0.000</cbc:Amount></cac:AllowanceCharge>
  <cac:TaxTotal><cbc:TaxAmount currencyID="JOD">{amt(tax)}</cbc:TaxAmount></cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:TaxExclusiveAmount currencyID="JOD">{amt(net)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="JOD">{amt(grand)}</cbc:TaxInclusiveAmount>
    <cbc:AllowanceTotalAmount currencyID="JOD">0.000</cbc:AllowanceTotalAmount>
    <cbc:PayableAmount currencyID="JOD">{amt(grand)}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
{chr(10).join(body)}
</Invoice>"""


def parse_response(payload: dict, status: int) -> dict:
    """Read QR/UUID/rejection defensively - the key names vary by response shape."""
    inner = payload.get("EINV_RESULTS") or {}
    inner = inner if isinstance(inner, dict) else {}
    qr = payload.get("QR_CODE") or payload.get("EINV_QR") or inner.get("QR_CODE") or inner.get("EINV_QR") or ""
    uid = payload.get("EINV_INV_UUID") or inner.get("EINV_INV_UUID") or ""
    errors = inner.get("ERRORS") or []
    reason = errors[0].get("EINV_MESSAGE") or errors[0].get("EINV_CODE") if errors and isinstance(errors[0], dict) else ""
    cleared = status in (200, 201) and bool(qr or uid)
    return {"cleared": cleared, "qr": qr, "uuid": uid, "reason": "" if cleared else (reason or str(payload)[:300])}


def submit(xml: str, client_id: str, secret_key: str, timeout=3):
    """timeout=3 is the 'instant attempt' budget; anything that fails goes to a retry queue."""
    r = requests.post(URL, json={"invoice": base64.b64encode(xml.encode("utf-8")).decode("ascii")},
                      headers={"Client-Id": client_id, "Secret-Key": secret_key}, timeout=timeout)
    try:
        payload = r.json()
    except ValueError:
        payload = {"error": r.text[:500]}
    return parse_response(payload, r.status_code)


if __name__ == "__main__":
    xml = build_xml(number="INV-0001", icv=1, tin="000000000", seller="Demo Restaurant",
                    income_source="0", lines=[("Shawarma sandwich", 2, "2.500"), ("Cola", 2, "0.500")])
    if "--send" not in sys.argv:
        print(xml)
        print("\n# dry run - request that would be sent:")
        print(json.dumps({"url": URL, "headers": ["Client-Id", "Secret-Key"], "body": {"invoice": "<base64 of the XML above>"}}, indent=2))
        sys.exit(0)
    cid, key = os.environ["JOFOTARA_CLIENT_ID"], os.environ["JOFOTARA_SECRET_KEY"]
    print(submit(xml, cid, key, timeout=15))
