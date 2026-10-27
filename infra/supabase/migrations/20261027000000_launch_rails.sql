-- Launch rails: waitlist, onboarding emails, customers and subscriptions.
-- All writes go through edge functions using the service role, so every table
-- has RLS enabled and no anon/authenticated policies.

create extension if not exists citext;
create extension if not exists pgcrypto;

-- Waitlist ------------------------------------------------------------------

create table if not exists public.waitlist (
    id               uuid primary key default gen_random_uuid(),
    email            citext not null unique,
    status           text not null default 'pending'
                     check (status in ('pending', 'confirmed', 'unsubscribed')),
    token            uuid not null default gen_random_uuid() unique,
    plan_interest    text,
    source           text,
    utm              jsonb not null default '{}'::jsonb,
    pain_point       text,
    onboarding_step  int not null default 0,
    confirmed_at     timestamptz,
    last_emailed_at  timestamptz,
    created_at       timestamptz not null default now()
);

create index if not exists waitlist_drip_idx
    on public.waitlist (status, onboarding_step, last_emailed_at);

-- Email templates & log -------------------------------------------------------
-- Templates are seeded by provision.py from the Copywriter agent's output, so
-- copy can change without redeploying functions. Variables use {{name}}.

create table if not exists public.email_templates (
    key         text primary key,
    subject     text not null,
    html        text not null,
    updated_at  timestamptz not null default now()
);

create table if not exists public.email_log (
    id            bigint generated always as identity primary key,
    email         citext not null,
    template_key  text not null,
    provider_id   text,
    error         text,
    created_at    timestamptz not null default now()
);

-- Billing -------------------------------------------------------------------

create table if not exists public.customers (
    id                  uuid primary key default gen_random_uuid(),
    email               citext not null unique,
    stripe_customer_id  text unique,
    created_at          timestamptz not null default now()
);

create table if not exists public.subscriptions (
    stripe_subscription_id  text primary key,
    customer_id             uuid not null references public.customers (id) on delete cascade,
    status                  text not null,
    price_lookup_key        text,
    current_period_end      timestamptz,
    cancel_at_period_end    boolean not null default false,
    updated_at              timestamptz not null default now()
);

create index if not exists subscriptions_customer_idx on public.subscriptions (customer_id);

-- Stripe retries webhooks; this table makes processing idempotent.
create table if not exists public.stripe_events (
    id           text primary key,
    type         text not null,
    received_at  timestamptz not null default now()
);

-- Lock everything down -------------------------------------------------------

alter table public.waitlist        enable row level security;
alter table public.email_templates enable row level security;
alter table public.email_log       enable row level security;
alter table public.customers       enable row level security;
alter table public.subscriptions   enable row level security;
alter table public.stripe_events   enable row level security;

-- Day-2 validation view: what people say they want and would pay for.
create or replace view public.waitlist_signals
with (security_invoker = true) as
select
    coalesce(plan_interest, 'none')                  as plan_interest,
    count(*)                                         as signups,
    count(*) filter (where status = 'confirmed')     as confirmed,
    count(*) filter (where status = 'unsubscribed')  as unsubscribed,
    count(pain_point)                                as pain_point_replies
from public.waitlist
group by 1
order by signups desc;
