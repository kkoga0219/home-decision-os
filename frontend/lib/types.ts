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
