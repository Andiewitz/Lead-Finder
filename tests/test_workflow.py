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


def test_reply_poll_suppresses_known_sender_once(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from src import db
    path = str(tmp_path / 'replies.db')
    monkeypatch.setattr(main, 'DB_PATH', path)
    monkeypatch.setattr(main, 'IMAP_USER', 'me@example.com')
    monkeypatch.setattr(main, 'IMAP_PASS', 'test')
    monkeypatch.setattr(main, 'OPENROUTER_API_KEY', None)
    db.init_db(path)
    lead_id = db.add_lead_record({'public_business_email': 'lead@example.com'}, db_path=path)
    db.mark_sent(lead_id, db_path=path)
    mail = MagicMock()
    message = b'From: Lead <lead@example.com>\r\nMessage-ID: <one@example.com>\r\nSubject: Re: Hello\r\n\r\nPlease unsubscribe me.'
    mail.uid.side_effect = lambda command, *args: ('OK', [b'1']) if command == 'search' else ('OK', [(b'1', message)])
    with patch('imaplib.IMAP4_SSL', return_value=mail), contextlib.redirect_stdout(io.StringIO()) as out:
        main.cmd_check_replies()
        main.cmd_check_replies()
    assert db.is_blacklisted('LEAD@example.com', path)
    assert '"suppressed": true' in out.getvalue()
    assert '"count": 0' in out.getvalue()


def test_ai_not_interested_is_not_classed_as_interested():
    from src import classifier
    response = {'choices': [{'message': {'content': 'Not interested'}}]}
    with patch('src.classifier.requests.post') as post:
        post.return_value.json.return_value = response
        assert classifier._classify_with_ai('no', 'key') == 'Not interested'


def test_mcp_tool_returns_protocol_content(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, LEAD_FINDER_PYTHON=sys.executable, DB_PATH=str(tmp_path / 'mcp.db'))
    requests = '\n'.join(json.dumps(x) for x in [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'get_stats', 'arguments': {}}},
    ]) + '\n'
    proc = subprocess.run(['node', str(root / 'src' / 'mcp_server.js')], input=requests,
                          text=True, capture_output=True, env=env, timeout=15, check=True)
    messages = [json.loads(line) for line in proc.stdout.splitlines()]
    assert len(messages) == 2
    result = next(m['result'] for m in messages if m.get('id') == 2)
    assert result['content'][0]['type'] == 'text'
    assert json.loads(result['content'][0]['text'])['success'] is True
