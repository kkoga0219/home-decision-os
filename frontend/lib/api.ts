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
