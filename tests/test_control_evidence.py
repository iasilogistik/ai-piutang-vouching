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



def test_unknown_signatures_do_not_create_reviewer_queue_when_stamp_is_clear():
    text = """
    Nomor SPJ 2501744403
    Checker
    Driver
    Satpam
    Penerima
    Stempel: Ada
    """

    result = analyze_spj_control_evidence(text)

    assert result["checker_signature"]["status"] == "UNKNOWN"
    assert result["driver_signature"]["status"] == "UNKNOWN"
    assert result["receiver_stamp"]["status"] == "PRESENT"
    assert result["review_required"] is False
    assert result["review_focus"] == "NONE"
    assert result["informational_reasons"]


def test_unreadable_stamp_is_reviewer_priority_even_when_signatures_are_only_unknown():
    text = """
    Nomor SPJ 2501744403
    Checker
    Driver
    Satpam
    Penerima
    """

    result = analyze_spj_control_evidence(text, expected_customer="TOKO SANTOSO")

    assert result["receiver_stamp"]["status"] == "UNKNOWN"
    assert result["review_required"] is True
    assert result["review_focus"] == "STAMP"
    assert any("stempel" in reason.lower() for reason in result["review_reasons"])


def test_explicit_missing_signature_still_requires_review():
    text = """
    Nomor SPJ 2501744403
    Tanda tangan checker: tidak ada
    Stempel: Ada
    """

    result = analyze_spj_control_evidence(text)

    assert result["checker_signature"]["status"] == "MISSING"
    assert result["review_required"] is True
    assert result["review_focus"] == "SIGNATURE_MISSING"
