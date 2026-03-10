/**
 * API client for Home Decision OS backend.
 *
 * In development the Next.js dev server runs on :3000 and the API on :8000.
 * In Docker we use the internal service name.
 */

import type {
  ComparisonResponse,
  EnrichmentResult,
  ExitScore,
  LoanScenario,
  LoanScenarioCreate,
  Property,
  PropertyCreate,
  RentalScenario,
  RentalScenarioCreate,
  RentEstimateResponse,
  URLPreviewResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// --- Properties ---

export async function listProperties(): Promise<Property[]> {
  return request("/properties");
}

export async function getProperty(id: number): Promise<Property> {
  return request(`/properties/${id}`);
}

export async function createProperty(data: PropertyCreate): Promise<Property> {
  return request("/properties", { method: "POST", body: JSON.stringify(data) });
}

export async function updateProperty(id: number, data: Partial<PropertyCreate>): Promise<Property> {
  return request(`/properties/${id}`, { method: "PATCH", body: JSON.stringify(data) });
}

export async function deleteProperty(id: number): Promise<void> {
  return request(`/properties/${id}`, { method: "DELETE" });
}

// --- Loan Scenarios ---

export async function listLoanScenarios(propertyId: number): Promise<LoanScenario[]> {
  return request(`/properties/${propertyId}/loan-scenarios`);
}

export async function createLoanScenario(propertyId: number, data: LoanScenarioCreate): Promise<LoanScenario> {
  return request(`/properties/${propertyId}/loan-scenarios`, { method: "POST", body: JSON.stringify(data) });
}

// --- Rental Scenarios ---

export async function listRentalScenarios(propertyId: number): Promise<RentalScenario[]> {
  return request(`/properties/${propertyId}/rental-scenarios`);
}

export async function createRentalScenario(propertyId: number, data: RentalScenarioCreate): Promise<RentalScenario> {
  return request(`/properties/${propertyId}/rental-scenarios`, { method: "POST", body: JSON.stringify(data) });
}

// --- Exit Score ---

export async function getExitScore(propertyId: number): Promise<ExitScore | null> {
  return request(`/properties/${propertyId}/exit-score`);
}

export async function calculateExitScore(propertyId: number): Promise<ExitScore> {
  return request(`/properties/${propertyId}/exit-score/calculate`, { method: "POST" });
}

// --- Comparison ---

export async function compareProperties(ids: number[]): Promise<ComparisonResponse> {
  return request("/comparison", { method: "POST", body: JSON.stringify({ property_ids: ids }) });
}

// --- Connectors ---

export async function fetchURLPreview(url: string): Promise<URLPreviewResponse> {
  return request("/connectors/url-preview", { method: "POST", body: JSON.stringify({ url }) });
}

export async function fetchRentEstimate(params: {
  price_jpy: number;
  floor_area_sqm?: number | null;
  built_year?: number | null;
  walking_minutes?: number | null;
  prefecture?: string;
}): Promise<RentEstimateResponse> {
  return request("/connectors/rent-estimate", { method: "POST", body: JSON.stringify(params) });
}

// --- Integrated Enrichment ---

export async function enrichFromURL(url: string): Promise<EnrichmentResult> {
  return request("/connectors/enrich-url", { method: "POST", body: JSON.stringify({ url }) });
}

export async function enrichFromData(params: {
  price_jpy: number;
  station_name?: string;
  address_text?: string;
  floor_area_sqm?: number | null;
  built_year?: number | null;
  walking_minutes?: number | null;
}): Promise<EnrichmentResult> {
  return request("/connectors/enrich-data", { method: "POST", body: JSON.stringify(params) });
}

// --- Area Search ---

export interface AreaSearchListing {
  url: string;
  name?: string;
  price_jpy?: number;
  price_text?: string;
  layout?: string;
  floor_area_sqm?: number;
  station_name?: string;
  walking_minutes?: number;
  built_year?: number;
  age_years?: number;
  floor?: string;
  estimated_rent?: number;
  gross_yield?: number;
  vs_market_pct?: number;
  vs_market?: string;
  parse_method?: string;
}

export interface AreaSearchResult {
  success: boolean;
  search_url: string;
  total_found: number;
  listings: AreaSearchListing[];
  area_stats: import("./types").AreaStats | null;
  errors: string[];
}

export async function searchArea(params: {
  station_name?: string;
  city_name?: string;
  search_url?: string;
  max_pages?: number;
}): Promise<AreaSearchResult> {
  return request("/connectors/area-search", { method: "POST", body: JSON.stringify(params) });
}

// --- Cashflow Simulation ---

export interface CashflowSimulationParams {
  price_jpy: number;
  floor_area_sqm?: number;
  built_year?: number | null;
  management_fee_jpy?: number;
  repair_reserve_jpy?: number;
  down_payment_jpy?: number;
  annual_interest_rate?: number;
  loan_years?: number;
  tax_credit_rate?: number;
  tax_credit_years?: number | null;
  tax_credit_max?: number;
  property_tax_annual?: number | null;
  insurance_annual?: number;
  scenario_type?: "self_use" | "investment";
  expected_rent_jpy?: number;
  vacancy_rate?: number;
  pm_fee_rate?: number;
  marginal_tax_rate?: number;
  simulation_years?: number;
  annual_price_decline_rate?: number;
}

export interface CashflowYearData {
  year: number;
  loan_payment: number;
  management_fee: number;
  repair_reserve: number;
  property_tax: number;
  insurance: number;
  total_expense: number;
  tax_credit: number;
  depreciation_benefit: number;
  gross_rent: number;
  vacancy_loss: number;
  pm_fee: number;
  net_rent: number;
  cashflow: number;
  cumulative_cashflow: number;
  outstanding_balance: number;
}

export interface ExitScenarioData {
  year: number;
  sale_price: number;
  outstanding_balance: number;
  selling_costs: number;
  capital_gain: number;
  cumulative_cashflow: number;
  total_return: number;
  annual_roi_pct: number;
}

export interface CashflowSimulationResult {
  price_jpy: number;
  scenario_type: string;
  initial_costs: {
    down_payment: number;
    broker_fee: number;
    registration_cost: number;
    acquisition_tax: number;
    loan_guarantee_fee: number;
    other_initial: number;
    total: number;
  };
  annual_cashflows: CashflowYearData[];
  exit_scenarios: ExitScenarioData[];
  summary_10yr: {
    total_cost: number;
    total_benefit: number;
    net_cost: number;
  };
}

export async function simulateCashflow(
  params: CashflowSimulationParams,
): Promise<CashflowSimulationResult> {
  return request("/cashflow/simulate", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function simulateCashflowForProperty(
  propertyId: number,
  params: Omit<CashflowSimulationParams, "price_jpy" | "floor_area_sqm" | "built_year" | "management_fee_jpy" | "repair_reserve_jpy">,
): Promise<CashflowSimulationResult> {
  return request(`/cashflow/properties/${propertyId}/simulate`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}
