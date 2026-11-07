import importlib
import pytest


def grading():
    assert importlib.util.find_spec('backend.grading'), 'missing grading implementation'
    return importlib.import_module('backend.grading')


SAMPLE = ('order_id,order_date,category,channel,quantity,unit_price,refund_amount\n'
          'a,2026-01-05,文具,线上,2,10.00,5.00\n'
          'b,2026-02-02,服饰,线下,1,30.00,0.00\n')


def test_refunds_are_deducted_and_order_count_is_not_quantity():
    result = grading().analyze_csv(SAMPLE.encode())
    assert result['totals'] == {'gross': 50.0, 'refund': 5.0, 'net': 45.0, 'orders': 2, 'aov': 22.5, 'refund_rate': 10.0}


def test_duplicates_and_invalid_rows_are_counted_without_inventing_values():
    content = SAMPLE + 'a,2026-01-05,文具,线上,2,10.00,5.00\n' + 'x,2026-01-05,文具,线上,,10.00,0.00\n'
    result = grading().analyze_csv(content.encode())
    assert result['duplicates'] == 1
    assert result['isolated'] == 1
    assert result['totals']['net'] == 45.0


def test_conflicting_duplicate_ids_are_all_isolated():
    content = SAMPLE + 'a,2026-01-05,文具,线上,2,20.00,5.00\n'
    result = grading().analyze_csv(content.encode())
    assert result['isolated'] == 2
    assert result['totals']['net'] == 30.0


@pytest.mark.parametrize('content', [b'wrong,columns\n1,2', b'\xff\xfe', b'x' * (2*1024*1024+1)], ids=['columns','encoding','oversize'])
def test_invalid_csv_rejected(content):
    with pytest.raises(ValueError):
        grading().analyze_csv(content)


def test_zero_denominator_is_unavailable():
    assert grading().change_rate(0, 20) is None
    assert grading().change_rate(100, 80) == -20.0


def test_wrong_values_do_not_claim_confirmed_cause_without_steps():
    mod = grading()
    expected = {'baseline_net': 100.0, 'current_net': 80.0, 'change_rate': -20.0, 'aov': 20.0, 'refund_rate': 20.0}
    result = mod.compare_metrics({'baseline_net':100,'current_net':100,'change_rate':-0.2,'aov':20,'refund_rate':0.2}, expected)
    assert result['score'] == 10
    assert result['error_tags'] == []
    diagnoses = {item['check_key']: item for item in result['diagnoses']}
    assert diagnoses['current_net']['status'] == 'insufficient'
    assert diagnoses['change_rate']['status'] == 'suspected'
    assert diagnoses['refund_rate']['status'] == 'suspected'
    assert all(item['probe']['question'] for item in diagnoses.values())


def test_reported_wrong_formula_requires_matching_intermediate_values():
    expected = {'current_net': 80.0}
    values = {'current_net': 100.0}
    confirmed = grading().compare_metrics(values, expected, {'current_net': {'formula': 'gross', 'gross': 100, 'refund': 20}})
    assert confirmed['diagnoses'][0]['status'] == 'confirmed_step_error'
    assert confirmed['error_tags'] == ['refund']
    inconsistent = grading().compare_metrics(values, expected, {'current_net': {'formula': 'gross', 'gross': 90, 'refund': 10}})
    assert inconsistent['diagnoses'][0]['status'] == 'suspected'
    assert inconsistent['error_tags'] == []


def test_clean_submission_must_preserve_real_orders():
    mod = grading()
    result = mod.evaluate_clean_csv(SAMPLE.encode(), 'A')
    assert not result['passed']
    assert result['score'] < 20


def test_a_b_training_have_distinct_answers_and_known_quality_cases():
    mod = grading()
    a, b = mod.reference('A'), mod.reference('B')
    assert a['quality']['duplicates'] == 5
    assert a['quality']['isolated'] == 3
    assert a['quality']['orders'] == 512
    assert a['metrics'] != b['metrics']


def test_quiz_has_independent_transfer_and_correct_scoring():
    course = importlib.import_module('backend.course') if importlib.util.find_spec('backend.course') else None
    assert course, 'missing course implementation'
    assert course.quiz_grade([1,0,2,1,2,0], 'C')['score'] == 6
    assert course.quiz_grade([0,0,0,0,0,0], 'C')['score'] == 2
