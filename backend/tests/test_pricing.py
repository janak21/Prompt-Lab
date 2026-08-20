"""Tests for backend.app.pricing."""

from __future__ import annotations

from backend.app.pricing import PRICES, cost, get_price, supports_prefill, supports_temperature


class TestCost:
    def test_known_model_computes_expected_cost(self) -> None:
        # claude-haiku-4-5: $1/mtok in, $5/mtok out
        result = cost("claude-haiku-4-5", 1_000_000, 1_000_000)
        assert result == 6.0

    def test_zero_tokens_zero_cost(self) -> None:
        assert cost("claude-sonnet-5", 0, 0) == 0.0

    def test_unknown_model_degrades_to_zero(self) -> None:
        assert cost("some-made-up-model", 1000, 1000) == 0.0

    def test_partial_tokens_scale_linearly(self) -> None:
        price = PRICES["claude-opus-5"]
        result = cost("claude-opus-5", 500_000, 200_000)
        expected = 0.5 * price.input_per_mtok + 0.2 * price.output_per_mtok
        assert abs(result - expected) < 1e-9

    def test_all_required_models_priced(self) -> None:
        for model in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"):
            assert model in PRICES
            assert PRICES[model].input_per_mtok > 0
            assert PRICES[model].output_per_mtok > 0


class TestGetPrice:
    def test_known_model(self) -> None:
        assert get_price("claude-haiku-4-5") is not None

    def test_unknown_model_returns_none(self) -> None:
        assert get_price("nonexistent") is None


class TestSupportsPrefill:
    def test_haiku_4_5_supports_prefill(self) -> None:
        assert supports_prefill("claude-haiku-4-5") is True

    def test_opus_5_does_not_support_prefill(self) -> None:
        assert supports_prefill("claude-opus-5") is False

    def test_sonnet_5_does_not_support_prefill(self) -> None:
        assert supports_prefill("claude-sonnet-5") is False

    def test_unknown_model_defaults_to_restrictive(self) -> None:
        # Unsafe direction would be to assume an unknown/future model supports prefill --
        # that produces a hard HTTP 400 at runtime as prefill is removed across new Claude
        # models. Defaulting to False routes unknown models through the always-safe
        # structured-outputs path instead.
        assert supports_prefill("some-future-model") is False


class TestSupportsTemperature:
    def test_haiku_4_5_supports_temperature(self) -> None:
        assert supports_temperature("claude-haiku-4-5") is True

    def test_opus_5_does_not_support_temperature(self) -> None:
        assert supports_temperature("claude-opus-5") is False

    def test_sonnet_5_does_not_support_temperature(self) -> None:
        assert supports_temperature("claude-sonnet-5") is False

    def test_unknown_model_defaults_to_restrictive(self) -> None:
        # Same safe direction as supports_prefill: sending temperature to a model that
        # has removed sampling parameters returns an opaque HTTP 400, while omitting it
        # for a model that never needed it is harmless.
        assert supports_temperature("some-future-model") is False

    def test_all_current_models_have_supports_temperature_flag(self) -> None:
        for model in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"):
            assert isinstance(PRICES[model].supports_temperature, bool)
