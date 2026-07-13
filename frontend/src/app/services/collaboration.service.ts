import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Collaborator {
  user_id: number;
  email: string;
  added_at: string;
}

export interface Review {
  id: number;
  job_id: number;
  user_id: number;
  user_email: string | null;
  rating: number;
  comment: string | null;
  created_at: string;
  updated_at: string;
  moderation_status: 'visible' | 'flagged' | 'hidden';
}

export interface AdminReview extends Review {
  job_display_name: string | null;
}

export interface ReviewsResponse {
  reviews: Review[];
  rating_average: number | null;
  rating_count: number;
}

export interface UserOut {
  id: number;
  email: string;
  role: string;
  tenant_id: number | null;
  is_active: number;
  department_id: number | null;
}

export interface Department {
  id: number;
  tenant_id: number;
  tenant_name: string | null;
  name: string;
}

export interface Tenant {
  id: number;
  name: string;
  is_active: number;
  created_at: string;
}

export interface TenantCreateResponse {
  tenant: Tenant;
  admin: { id: number; email: string };
}

export interface UsageUser {
  user_id: number;
  email: string;
  department_id: number | null;
  department_name: string | null;
  presentations_created: number;
  edits: number;
  time_spent_seconds: number;
  rating_average_received: number | null;
}

export interface UsageReport {
  id: number;
  tenant_id: number | null;
  period_start: string;
  period_end: string;
  payload: {
    presentations_created: number;
    total_edits: number;
    total_time_spent_seconds: number;
    rating_average: number | null;
    contributors_count: number;
    top_user: { user_id: number; email: string | null; activity_total: number } | null;
    top_department: { department_id: number; name: string | null; activity_total: number } | null;
  };
  created_at: string;
  sent_at: string | null;
}

export interface BadgeTier {
  threshold: number;
  label: string;
}

export interface MyBadges {
  count: number;
  current_badge: BadgeTier | null;
  next_badge: BadgeTier | null;
  progress_to_next: number | null;
}

@Injectable({ providedIn: 'root' })
export class CollaborationService {
  private apiUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  // --- Collaborators ---
  getCollaborators(jobId: number): Observable<Collaborator[]> {
    return this.http.get<Collaborator[]>(`${this.apiUrl}/presentations/${jobId}/collaborators`);
  }

  addCollaborator(jobId: number, userId: number): Observable<{ user_id: number; added_at: string }> {
    return this.http.post<{ user_id: number; added_at: string }>(`${this.apiUrl}/presentations/${jobId}/collaborators`, { user_id: userId });
  }

  removeCollaborator(jobId: number, userId: number): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(`${this.apiUrl}/presentations/${jobId}/collaborators/${userId}`);
  }

  // --- Reviews ---
  getReviews(jobId: number): Observable<ReviewsResponse> {
    return this.http.get<ReviewsResponse>(`${this.apiUrl}/presentations/${jobId}/reviews`);
  }

  upsertReview(jobId: number, rating: number, comment?: string): Observable<Review> {
    return this.http.post<Review>(`${this.apiUrl}/presentations/${jobId}/reviews`, { rating, comment });
  }

  deleteOwnReview(jobId: number): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(`${this.apiUrl}/presentations/${jobId}/reviews/me`);
  }

  // --- Users (admin management) ---
  getUsers(): Observable<UserOut[]> {
    return this.http.get<UserOut[]>(`${this.apiUrl}/users`);
  }

  // --- User directory (any authenticated user, minimal fields — collaborator picker) ---
  getUserDirectory(): Observable<{ id: number; email: string }[]> {
    return this.http.get<{ id: number; email: string }[]>(`${this.apiUrl}/users/directory`);
  }

  // --- Departments ---
  getDepartments(tenantId?: number): Observable<Department[]> {
    let params = new HttpParams();
    if (tenantId !== undefined) params = params.set('tenant_id', tenantId);
    return this.http.get<Department[]>(`${this.apiUrl}/admin/departments`, { params });
  }

  createDepartment(name: string, tenantId?: number): Observable<Department> {
    return this.http.post<Department>(`${this.apiUrl}/admin/departments`, { name, tenant_id: tenantId });
  }

  deleteDepartment(departmentId: number): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(`${this.apiUrl}/admin/departments/${departmentId}`);
  }

  updateUserDepartment(userId: number, departmentId: number | null): Observable<UserOut> {
    return this.http.patch<UserOut>(`${this.apiUrl}/users/${userId}/department`, { department_id: departmentId });
  }

  // --- Tenants (superadmin only) ---
  getTenants(): Observable<Tenant[]> {
    return this.http.get<Tenant[]>(`${this.apiUrl}/admin/tenants`);
  }

  createTenant(name: string, adminEmail: string, adminPassword: string): Observable<TenantCreateResponse> {
    return this.http.post<TenantCreateResponse>(`${this.apiUrl}/admin/tenants`, {
      name,
      admin_email: adminEmail,
      admin_password: adminPassword,
    });
  }

  // --- Analytics & Reports ---
  getUsageAnalytics(tenantId?: number): Observable<{ users: UsageUser[] }> {
    let params = new HttpParams();
    if (tenantId !== undefined) params = params.set('tenant_id', tenantId);
    return this.http.get<{ users: UsageUser[] }>(`${this.apiUrl}/admin/analytics/usage`, { params });
  }

  getUsageReports(tenantId?: number): Observable<UsageReport[]> {
    let params = new HttpParams();
    if (tenantId !== undefined) params = params.set('tenant_id', tenantId);
    return this.http.get<UsageReport[]>(`${this.apiUrl}/admin/usage-reports`, { params });
  }

  // --- Moderation ---
  getAdminReviews(statusFilter?: string): Observable<AdminReview[]> {
    let params = new HttpParams();
    if (statusFilter) params = params.set('status_filter', statusFilter);
    return this.http.get<AdminReview[]>(`${this.apiUrl}/admin/reviews`, { params });
  }

  updateReviewModeration(reviewId: number, status: 'visible' | 'hidden'): Observable<Review> {
    return this.http.patch<Review>(`${this.apiUrl}/admin/reviews/${reviewId}/moderation`, { status });
  }

  getModerationBlocklist(): Observable<{ terms: string[] }> {
    return this.http.get<{ terms: string[] }>(`${this.apiUrl}/admin/config/review-moderation-blocklist`);
  }

  updateModerationBlocklist(terms: string[]): Observable<{ terms: string[] }> {
    return this.http.patch<{ terms: string[] }>(`${this.apiUrl}/admin/config/review-moderation-blocklist`, { terms });
  }

  // --- Badges ---
  getMyBadges(): Observable<MyBadges> {
    return this.http.get<MyBadges>(`${this.apiUrl}/users/me/badges`);
  }
}
