import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../services/auth.service';
import {
  CollaborationService,
  Department,
  UserOut,
  AdminReview,
  UsageUser,
  UsageReport,
  Tenant,
} from '../../services/collaboration.service';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.css'
})
export class AdminComponent implements OnInit {
  private collaborationService = inject(CollaborationService);
  private authService = inject(AuthService);

  activeTab: 'tenants' | 'departments' | 'moderation' | 'analytics' | 'reports' = 'departments';

  get isSuperadmin(): boolean {
    return this.authService.currentUser?.role === 'superadmin';
  }

  // --- TENANTS (superadmin only) ---
  tenants: Tenant[] = [];
  newTenantName = '';
  newTenantAdminEmail = '';
  newTenantAdminPassword = '';
  tenantError = '';
  tenantCreated = '';

  // --- DEPARTMENTS & USERS (share one tenant scope, superadmin only) ---
  // A superadmin must pick which tenant they're managing before departments/users
  // load, so the two lists are always drawn from the same tenant — picking a user
  // from one tenant and a department from another used to 403 on assign.
  selectedTenantId: number | null = null;

  departments: Department[] = [];
  newDepartmentName = '';
  departmentError = '';

  users: UserOut[] = [];
  newUserEmail = '';
  newUserPassword = '';
  userError = '';
  assignUserId: number | null = null;
  assignDepartmentId: number | null = null;
  assignError = '';

  // --- MODERATION ---
  adminReviews: AdminReview[] = [];
  moderationFilter: '' | 'visible' | 'flagged' | 'hidden' = 'flagged';
  blocklistTerms: string[] = [];
  blocklistText = '';
  blocklistSaved = false;

  // --- ANALYTICS ---
  usageUsers: UsageUser[] = [];
  analyticsTenantId: number | null = null;

  // --- REPORTS ---
  usageReports: UsageReport[] = [];
  reportsTenantId: number | null = null;

  ngOnInit() {
    if (this.isSuperadmin) { this.loadTenants(); }
    this.setTab('departments');
  }

  setTab(tab: 'tenants' | 'departments' | 'moderation' | 'analytics' | 'reports') {
    this.activeTab = tab;
    if (tab === 'tenants') { this.loadTenants(); }
    if (tab === 'departments') { this.loadDepartments(); this.loadUsers(); }
    if (tab === 'moderation') { this.loadAdminReviews(); this.loadBlocklist(); }
    if (tab === 'analytics') { this.loadAnalytics(); }
    if (tab === 'reports') { this.loadReports(); }
  }

  // --- TENANTS ---

  loadTenants() {
    if (!this.isSuperadmin) return;
    this.collaborationService.getTenants().subscribe({
      next: (res) => this.tenants = res,
      error: () => {}
    });
  }

  createTenant() {
    const name = this.newTenantName.trim();
    const email = this.newTenantAdminEmail.trim();
    if (!name || !email || !this.newTenantAdminPassword) return;
    this.tenantError = '';
    this.tenantCreated = '';
    this.collaborationService.createTenant(name, email, this.newTenantAdminPassword).subscribe({
      next: (res) => {
        this.tenantCreated = `Tenant "${res.tenant.name}" created — admin ${res.admin.email} can now log in with the password you set.`;
        this.newTenantName = '';
        this.newTenantAdminEmail = '';
        this.newTenantAdminPassword = '';
        this.loadTenants();
      },
      error: (err) => { this.tenantError = err.error?.detail || 'Could not create tenant.'; }
    });
  }

  tenantName(id: number | null): string {
    if (!id) return '—';
    return this.tenants.find(t => t.id === id)?.name || '—';
  }

  // --- DEPARTMENTS & USERS ---

  onTenantScopeChange() {
    // Switching tenant invalidates any user/department picked from the old scope.
    this.assignUserId = null;
    this.assignDepartmentId = null;
    this.loadDepartments();
    this.loadUsers();
  }

  loadDepartments() {
    this.collaborationService.getDepartments(this.isSuperadmin && this.selectedTenantId ? this.selectedTenantId : undefined).subscribe({
      next: (res) => this.departments = res,
      error: () => {}
    });
  }

  loadUsers() {
    this.collaborationService.getUsers(this.isSuperadmin && this.selectedTenantId ? this.selectedTenantId : undefined).subscribe({
      next: (res) => this.users = res,
      error: () => {}
    });
  }

  createDepartment() {
    const name = this.newDepartmentName.trim();
    if (!name) return;
    if (this.isSuperadmin && !this.selectedTenantId) return;
    this.departmentError = '';
    this.collaborationService.createDepartment(name, this.isSuperadmin ? (this.selectedTenantId ?? undefined) : undefined).subscribe({
      next: () => {
        this.newDepartmentName = '';
        this.loadDepartments();
      },
      error: (err) => { this.departmentError = err.error?.detail || 'Could not create department.'; }
    });
  }

  deleteDepartment(d: Department) {
    this.departmentError = '';
    this.collaborationService.deleteDepartment(d.id).subscribe({
      next: () => this.loadDepartments(),
      error: (err) => { this.departmentError = err.error?.detail || 'Could not delete department.'; }
    });
  }

  createUser() {
    const email = this.newUserEmail.trim();
    if (!email || !this.newUserPassword) return;
    if (this.isSuperadmin && !this.selectedTenantId) return;
    this.userError = '';
    this.collaborationService.createUser(email, this.newUserPassword, this.isSuperadmin ? (this.selectedTenantId ?? undefined) : undefined).subscribe({
      next: () => {
        this.newUserEmail = '';
        this.newUserPassword = '';
        this.loadUsers();
      },
      error: (err) => { this.userError = err.error?.detail || 'Could not create user.'; }
    });
  }

  assignDepartment() {
    if (!this.assignUserId) return;
    this.assignError = '';
    this.collaborationService.updateUserDepartment(this.assignUserId, this.assignDepartmentId).subscribe({
      next: () => {
        this.loadUsers();
      },
      error: (err) => { this.assignError = err.error?.detail || 'Could not assign department.'; }
    });
  }

  departmentName(id: number | null): string {
    if (!id) return '—';
    return this.departments.find(d => d.id === id)?.name || '—';
  }

  // --- MODERATION ---

  loadAdminReviews() {
    this.collaborationService.getAdminReviews(this.moderationFilter || undefined).subscribe({
      next: (res) => this.adminReviews = res,
      error: () => {}
    });
  }

  setModerationStatus(review: AdminReview, status: 'visible' | 'hidden') {
    this.collaborationService.updateReviewModeration(review.id, status).subscribe({
      next: () => this.loadAdminReviews(),
      error: () => {}
    });
  }

  loadBlocklist() {
    if (!this.isSuperadmin) return;
    this.collaborationService.getModerationBlocklist().subscribe({
      next: (res) => {
        this.blocklistTerms = res.terms;
        this.blocklistText = res.terms.join(', ');
      },
      error: () => {}
    });
  }

  saveBlocklist() {
    const terms = this.blocklistText.split(',').map(t => t.trim()).filter(t => t.length > 0);
    this.collaborationService.updateModerationBlocklist(terms).subscribe({
      next: (res) => {
        this.blocklistTerms = res.terms;
        this.blocklistSaved = true;
        setTimeout(() => this.blocklistSaved = false, 2000);
      },
      error: () => {}
    });
  }

  // --- ANALYTICS ---

  loadAnalytics() {
    this.collaborationService.getUsageAnalytics(this.analyticsTenantId ?? undefined).subscribe({
      next: (res) => this.usageUsers = res.users,
      error: () => {}
    });
  }

  formatMinutes(seconds: number): string {
    return Math.round(seconds / 60) + ' min';
  }

  // --- REPORTS ---

  loadReports() {
    this.collaborationService.getUsageReports(this.reportsTenantId ?? undefined).subscribe({
      next: (res) => this.usageReports = res,
      error: () => {}
    });
  }
}
