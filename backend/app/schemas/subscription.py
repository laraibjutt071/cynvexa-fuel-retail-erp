import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.subscription import BillingCycle, SubscriptionStatus
from app.models.subscription_payment import SubscriptionPaymentStatus
from app.schemas.plan import PlanRead


class SubscriptionCreate(BaseModel):
    """Platform-admin only: assign a subscription to an organization that
    doesn't have one yet. Starts in TRIAL unless status is given explicitly."""

    plan_id: uuid.UUID
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    status: SubscriptionStatus = SubscriptionStatus.TRIAL
    trial_ends_at: datetime | None = None
    current_period_start: datetime
    current_period_end: datetime


class SubscriptionUpdate(BaseModel):
    """Platform-admin only: change plan, cycle, status or period - e.g. to
    renew, cancel, upgrade/downgrade, or correct a mistake. Every change is
    audit-logged with before/after (see app/api/platform.py)."""

    plan_id: uuid.UUID | None = None
    billing_cycle: BillingCycle | None = None
    status: SubscriptionStatus | None = None
    trial_ends_at: datetime | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    canceled_at: datetime | None = None


class SubscriptionRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    plan_id: uuid.UUID
    plan: PlanRead
    status: SubscriptionStatus
    billing_cycle: BillingCycle
    trial_ends_at: datetime | None
    current_period_start: datetime
    current_period_end: datetime
    canceled_at: datetime | None

    model_config = {"from_attributes": True}


class SubscriptionPaymentCreate(BaseModel):
    """Platform-admin only: record a payment the admin is personally
    attesting was received and verified - see SubscriptionPayment's model
    docstring for why there is no separate unverified/pending state."""

    amount: Decimal = Field(gt=0, decimal_places=2)
    method: str = Field(min_length=1, max_length=50)
    reference: str | None = Field(default=None, max_length=200)
    status: SubscriptionPaymentStatus = SubscriptionPaymentStatus.VERIFIED
    period_start: datetime
    period_end: datetime
    notes: str | None = None


class SubscriptionPaymentRead(BaseModel):
    id: uuid.UUID
    subscription_id: uuid.UUID
    amount: Decimal
    method: str
    reference: str | None
    status: SubscriptionPaymentStatus
    period_start: datetime
    period_end: datetime
    notes: str | None
    recorded_by_user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
