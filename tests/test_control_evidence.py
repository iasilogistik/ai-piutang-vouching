from app.services.control_evidence import analyze_spj_control_evidence, compare_stamp_to_customer


def test_detects_checker_signature_when_explicitly_marked_present():
    text = """
    Nomor SPJ 2501787882
    Checker Signature: Ada
    Driver TTD: Ada
    Security TTD: Ada
    BM TTD: Ada
    Stempel: Ada
    TOKO SANTOSO
    """

    result = analyze_spj_control_evidence(text, expected_customer="SANTOSO, TOKO")

    assert result["checker_signature"]["status"] == "PRESENT"
    assert result["driver_signature"]["status"] == "PRESENT"
    assert result["security_signature"]["status"] == "PRESENT"
    assert result["bm_signature"]["status"] == "PRESENT"
    assert result["receiver_stamp"]["status"] == "PRESENT"
    assert result["receiver_stamp"]["customer_match"]["status"] == "MATCH"


def test_role_label_without_signature_is_manual_review_not_guess():
    text = """
    Nomor SPJ 2501744403
    Checker
    Driver
    Satpam
    Penerima
    """

    result = analyze_spj_control_evidence(text)

    assert result["checker_signature"]["status"] == "UNKNOWN"
    assert result["driver_signature"]["status"] == "UNKNOWN"
    assert result["security_signature"]["status"] == "UNKNOWN"
    assert result["receiver_signature"]["status"] == "UNKNOWN"
    assert result["review_required"] is True
    assert result["review_reasons"]


def test_stamp_customer_mismatch_goes_to_review():
    comparison = compare_stamp_to_customer("TB BERKAH JAYA", "TOKO SANTOSO")

    assert comparison["status"] == "REVIEW"
    assert "cek manual" in comparison["remarks"]
