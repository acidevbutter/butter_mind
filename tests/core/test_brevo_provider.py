from app.core.email.brevo_provider import _dns_records_from_payload


def test_dns_records_from_payload_flattens_brevo_dict_shape():
    payload = {
        "id": 123,
        "domain_name": "acme.com",
        "dns_records": {
            "brevo_code": {
                "host_name": "acme.com",
                "type": "txt",
                "value": "brevo-code:abc123",
                "status": False,
            },
            "dkim_record": {
                "host_name": "mail._domainkey.acme.com",
                "type": "txt",
                "value": "k=rsa; p=...",
                "status": True,
            },
        },
    }

    records = _dns_records_from_payload(payload)

    assert len(records) == 2
    by_host = {r.host_name: r for r in records}
    assert by_host["acme.com"].verified is False
    assert by_host["mail._domainkey.acme.com"].verified is True
    assert all(r.record_type == "txt" for r in records)


def test_dns_records_from_payload_handles_missing_dns_records_key():
    assert _dns_records_from_payload({"id": 1, "domain_name": "acme.com"}) == []
