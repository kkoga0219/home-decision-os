/** Mirrors the backend Pydantic schemas exactly. */

export interface Property {
  id: number;
  name: string;
  source_url: string | null;
  address_text: string | null;
  station_name: string | null;
  walking_minutes: number | null;
  price_jpy: number;
  floor_area_sqm: number | null;
  layout: string | null;
  built_year: number | null;
  management_fee_jpy: number | null;
  repair_reserve_jpy: number | null;
  floor_number: number | null;
  total_floors: number | null;
  total_units: number | null;
  zoning_type: string | null;
  hazard_flag: boolean | null;
  memo: string | null;
  created_at: string;
  updated_at: string;
}

export interface PropertyCreate {
  name: string;
  source_url?: string | null;
  address_text?: string | null;
  station_name?: string | null;
  walking_minutes?: number | null;
  price_jpy: number;
  floor_area_sqm?: number | null;
  layout?: string | null;
  built_year?: number | null;
  management_fee_jpy?: number | null;
  repair_reserve_jpy?: number | null;
  floor_number?: number | null;
  total_floors?: number | null;
  total_units?: number | null;
  zoning_type?: string | null;
  hazard_flag?: boolean | null;
  memo?: string | null;
}

export interface LoanScenario {
  id: number;
  property_id: number;
  label: string | null;
  down_payment_jpy: number;
  loan_amount_jpy: number;
  annual_interest_rate: number;
  loan_years: number;
  tax_credit_rate: number;
  tax_credit_years: number;
  monthly_payment_jpy: number;
  annual_payment_jpy: number;
  total_payment_jpy: number;
  created_at: string;
}

export interface LoanScenarioCreate {
  label?: string | null;
  down_payment_jpy?: number;
  annual_interest_rate: number;
  loan_years: number;
  tax_credit_rate?: number;
  tax_credit_years?: number;
}

export interface RentalScenario {
  id: number;
  property_id: number;
  label: string | null;
  expected_rent_jpy: number;
  vacancy_rate: number;
  management_fee_rate: number;
  insurance_annual_jpy: number;
  fixed_asset_tax_annual_jpy: number;
  other_cost_annual_jpy: number;
  monthly_net_cashflow_jpy: number | null;
  created_at: string;
}

export interface RentalScenarioCreate {
  label?: string | null;
  expected_rent_jpy: number;
  vacancy_rate?: number;
  management_fee_rate?: number;
  insurance_annual_jpy?: number;
  fixed_asset_tax_annual_jpy?: number;
  other_cost_annual_jpy?: number;
}

export interface ExitScore {
  id: number;
  property_id: number;
  station_score: number;
  size_score: number;
  layout_score: number;
  age_score: number;
  zoning_score: number;
  hazard_score: number;
  liquidity_score: number;
  total_score: number;
  assessment: string | null;
  created_at: string;
}

export interface PropertySummary {
  property: Property;
  loan_scenarios: LoanScenario[];
  rental_scenarios: RentalScenario[];
  exit_score: ExitScore | null;
}

export interface ComparisonResponse {
  properties: PropertySummary[];
}

// --- Connector types ---

export interface URLPreviewResponse {
  success: boolean;
  data: {
    url?: string;
    title?: string;
    description?: string;
    image?: string;
    site_name?: string;
    hint_price_jpy?: number;
    hint_floor_area_sqm?: number;
    hint_layout?: string;
    hint_walking_minutes?: number;
    hint_station_name?: string;
    hint_built_year?: number;
    hint_address_text?: string;
    hint_management_fee_jpy?: number;
    hint_repair_reserve_jpy?: number;
    hint_total_units?: number;
    hint_floor_number?: number;
    hint_total_floors?: number;
  };
  errors: string[];
}

export interface RentEstimateResponse {
  success: boolean;
  estimated_rent: number;
  low_estimate: number;
  high_estimate: number;
  gross_yield: number;
  method: string;
  confidence?: string;
}

export interface AreaStats {
  area_name: string;
  prefecture: string;
  avg_unit_price_sqm: number;
  avg_price_70sqm: number;
  avg_rent_per_sqm: number;
  avg_gross_yield: number;
  transaction_count_annual: number;
  price_trend: string;
  population_trend: string;
  source: string;
  note?: string;
}

export interface MarketComparison {
  your_price_70sqm_normalized: number;
  area_avg_70sqm: number;
  diff_percent: number;
  assessment: string;
}

export interface EnrichmentResult {
  url?: string;
  title?: string;
  description?: string;
  image?: string;
  sources_used: string[];
  errors: string[];
  // Hints from URL
  hint_price_jpy?: number;
  hint_floor_area_sqm?: number;
  hint_layout?: string;
  hint_walking_minutes?: number;
  hint_station_name?: string;
  hint_built_year?: number;
  hint_address_text?: string;
  hint_management_fee_jpy?: number;
  hint_repair_reserve_jpy?: number;
  hint_total_units?: number;
  hint_floor_number?: number;
  hint_total_floors?: number;
  // Enriched data
  area_stats?: AreaStats;
  rent_estimate?: RentEstimateResponse;
  market_comparison?: MarketComparison;
  url_preview?: Record<string, unknown>;
  mlit_data?: Record<string, unknown>;
}
