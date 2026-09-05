from unittest.mock import patch, MagicMock
import pytest
from app.social.providers.reddit import RedditProvider
from app.social.schemas import SocialProviderError, SocialPost

def test_reddit_provider_missing_credentials():
    # Without credentials, provider should handle gracefully (e.g. return empty list or raise recoverable error)
    with patch.dict("os.environ", {}, clear=True):
        provider = RedditProvider(client_id=None, client_secret=None, user_agent=None)
        assert provider.is_configured is False
        posts = provider.search(query="NVDA", limit=10)
        assert posts == []

def test_reddit_provider_search_success():
    provider = RedditProvider(client_id="id", client_secret="secret", user_agent="test/0.1")
    assert provider.is_configured is True
    
    mock_submission = MagicMock()
    mock_submission.id = "sub123"
    mock_submission.title = "NVDA earnings discussion"
    mock_submission.selftext = "What are your plays?"
    mock_submission.score = 250
    mock_submission.num_comments = 80
    mock_submission.upvote_ratio = 0.95
    mock_submission.permalink = "/r/stocks/comments/sub123"
    mock_submission.created_utc = 1725537600
    mock_submission.author = MagicMock()
    mock_submission.author.name = "deep_value"
    mock_submission.link_flair_text = "Earnings"

    with patch.object(provider, "_fetch_submissions", return_value=[mock_submission]):
        posts = provider.search(query="NVDA", limit=5)
        assert len(posts) == 1
        post = posts[0]
        assert post.post_id == "reddit_sub123"
        assert post.author == "deep_value"
        assert post.score == 250
        assert post.flair == "Earnings"
        assert post.url == "https://reddit.com/r/stocks/comments/sub123"
