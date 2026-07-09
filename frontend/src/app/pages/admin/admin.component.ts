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

  activeTab: 'departments' | 'moderation' | 'analytics' | 'reports' = 'departments';

  get isSuperadmin(): boolean {
    return this.authService.currentUser?.role === 'superadmin';
  }

  // --- DEPARTMENTS ---
  departments: Department[] = [];
  newDepartmentName = '';
  newDepartmentTenantId: number | null = null;
  departmentError = '';

  users: UserOut[] = [];
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
    this.setTab('departments');
  }

  setTab(tab: 'departments' | 'moderation' | 'analytics' | 'reports') {
    this.activeTab = tab;
    if (tab === 'departments') { this.loadDepartments(); this.loadUsers(); }
    if (tab === 'moderation') { this.loadAdminReviews(); this.loadBlocklist(); }
    if (tab === 'analytics') { this.loadAnalytics(); }
    if (tab === 'reports') { this.loadReports(); }
  }

  // --- DEPARTMENTS ---

  loadDepartments() {
    this.collaborationService.getDepartments(this.isSuperadmin && this.newDepartmentTenantId ? this.newDepartmentTenantId : undefined).subscribe({
      next: (res) => this.departments = res,
      error: () => {}
    });
  }

  loadUsers() {
    this.collaborationService.getUsers().subscribe({
      next: (res) => this.users = res,
      error: () => {}
    });
  }

  createDepartment() {
    const name = this.newDepartmentName.trim();
    if (!name) return;
    this.departmentError = '';
    this.collaborationService.createDepartment(name, this.isSuperadmin ? (this.newDepartmentTenantId ?? undefined) : undefined).subscribe({
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
