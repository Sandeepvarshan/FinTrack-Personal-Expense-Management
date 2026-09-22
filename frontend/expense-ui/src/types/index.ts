export type User = { id: number; name: string; email: string; created_at: string };
export type Expense = { id: number; description: string; amount: number; expense_date: string; payment_method: string; category_id: number };
export type Category = { id: number; name: string; description?: string };
export type Budget = { id: number; category_id?: number; month: number; year: number; amount: number; spent: number; remaining: number; percentage_used: number; status: string };
export type Notification = { id: number; message: string; type: string; is_read: boolean; created_at: string };
export type CategoryReport = { category_id: number; category_name: string; total_amount: number; percentage: number };
export type YearlyReport = { month: number; total_expenses: number; transaction_count: number };
export type BudgetVsActualReport = { budget_id: number; category_id?: number; category_name?: string; month: number; year: number; budget_amount: number; actual_amount: number; variance: number; percentage_used: number; status: string };