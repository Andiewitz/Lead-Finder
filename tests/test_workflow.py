import argparse
import contextlib
import io
import json
from unittest.mock import patch
from src import main


def test_find_leads_uses_requested_search_and_does_not_send(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', str(tmp_path / 'leads.db'))
    monkeypatch.setattr(main, 'SEARCH_API_KEY', 'test')
    main.db.init_db(main.DB_PATH)
    candidate = {'title': 'Example', 'url': 'https://example.com', 'content': 'hello@example.com'}
    out = io.StringIO()
    with patch.object(main.discovery, 'discover_leads', return_value=[candidate]) as find, \
         patch.object(main.sender, 'send_email') as send, contextlib.redirect_stdout(out):
        main.cmd_find_leads(argparse.Namespace(industry='plumber', location='Seattle', count=2))
    find.assert_called_once_with('plumber', 'Seattle', main.SEARCH_API_URL, 'test', count=2)
    send.assert_not_called()
    lead = json.loads(out.getvalue())['leads'][0]
    assert lead['location'] == 'Seattle'
    assert lead['qualification_status'] == 'needs review'


def test_send_reservation_enforces_suppression_and_quota(tmp_path):
    from src import db
    import pytest
    path = str(tmp_path / 'reserve.db')
    db.init_db(path)
    db.add_to_blacklist('Example.COM', db_path=path)
    with pytest.raises(ValueError, match='do-not-contact'):
        db.reserve_send({'public_business_email': 'person@example.com'}, 2, path)
    first = db.reserve_send({'public_business_email': 'A@other.com'}, 1, path)
    with pytest.raises(ValueError, match='already'):
        db.reserve_send({'public_business_email': 'a@OTHER.com'}, 2, path)
    with pytest.raises(ValueError, match='limit'):
        db.reserve_send({'public_business_email': 'b@other.com'}, 1, path)
    db.mark_sent(first, db_path=path)
    assert db.get_stats(path)['sent_today'] == 1
