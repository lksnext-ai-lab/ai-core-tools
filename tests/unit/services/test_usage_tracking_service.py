from unittest.mock import MagicMock

from services.usage_tracking_service import UsageTrackingService


def test_record_system_llm_call_tracks_usage_in_self_managed_mode(mocker):
    record = MagicMock()
    usage_repository = mocker.patch(
        "services.usage_tracking_service.UsageRecordRepository"
    )
    usage_repository.return_value.increment.return_value = record
    mocker.patch(
        "services.usage_tracking_service.is_self_managed",
        return_value=True,
    )
    subscription_repository = mocker.patch(
        "services.usage_tracking_service.SubscriptionRepository"
    )

    result = UsageTrackingService.record_system_llm_call(MagicMock(), user_id=42)

    assert result is record
    usage_repository.return_value.increment.assert_called_once_with(42)
    subscription_repository.assert_not_called()
