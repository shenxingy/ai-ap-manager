// ─── Invoice Detail Types ───

export interface ExtractedField {
  value: string | null;
  confidence: number | null;
  is_overridden?: boolean;
}

export interface ExtractionResult {
  pass_number: 1 | 2;
  extracted_fields: Record<string, unknown>;
  discrepancy_fields: string[];
}

export interface Invoice {
  id: string;
  invoice_number: string;
  vendor_name_raw: string;
  vendor_id?: string;
  total_amount: number;
  status: string;
  fraud_score: number | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string;
  created_at: string;
  is_recurring?: boolean;
  is_duplicate?: boolean;
  confidence_score?: number | null;
  extracted_fields?: Record<string, ExtractedField>;
  extraction_results?: ExtractionResult[];
  payment_status?: string | null;
  payment_date?: string | null;
  payment_method?: string | null;
  payment_reference?: string | null;
  normalized_amount_usd?: number | null;
  fx_rate_used?: number | null;
  fx_rate_date?: string | null;
}

export interface LineItem {
  id: string;
  description: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  gl_code: string | null;
  gl_suggestion: string | null;
  gl_suggestion_confidence?: number | null;
  cost_center?: string | null;
}

export interface GRLineOut {
  id: string;
  line_number: number;
  description: string;
  qty_received: number;
  unit: string | null;
}

export interface GRNSummaryOut {
  id: string;
  gr_number: string;
  received_at: string;
  lines: GRLineOut[];
  inspection_status: string | null;
}

export interface LineItemMatchOut {
  id: string;
  match_result_id: string;
  invoice_line_id: string;
  po_line_id: string | null;
  gr_line_id: string | null;
  status: string; // matched, qty_variance, price_variance, unmatched
  qty_variance: number | null;
  price_variance: number | null;
  price_variance_pct: number | null;
  created_at: string;
  // Enriched fields
  description: string | null;
  invoice_amount: number | null;
  po_amount: number | null;
  qty_invoiced: number | null;
  qty_on_po: number | null;
  qty_received: number | null;
  exception_code: string | null;
  grn_lines_used: string[] | null;
}

export interface MatchResult {
  id: string;
  match_type: string; // 2way, 3way, non_po
  match_status: string;
  po_id: string | null;
  gr_id: string | null;
  amount_variance: number | null;
  amount_variance_pct: number | null;
  matched_at: string | null;
  notes: string | null;
  line_matches: LineItemMatchOut[];
  // Enriched
  po_number: string | null;
  gr_number: string | null;
  grn_data: GRNSummaryOut | null;
}

export interface ExceptionItem {
  id: string;
  code: string;
  severity: string;
  status: string;
  description: string;
  created_at: string;
}

export interface ApprovalTask {
  id: string;
  status: string;
  assignee_name: string;
  assigned_at: string;
  decided_at: string | null;
  notes: string | null;
  chain_step: number | null;
  chain_total: number | null;
}

export interface AuditEntry {
  id: string;
  action: string;
  actor: string;
  created_at: string;
  detail: string | null;
}

export interface VendorMessage {
  id: string;
  body: string;
  is_internal: boolean;
  direction: "inbound" | "outbound";
  sender_email: string | null;
  created_at: string;
}

export interface ComplianceDoc {
  id: string;
  status: string;
}
