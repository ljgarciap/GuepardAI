/**
 * collaboration.service.spec.ts — verifica método/URL/payload de cada
 * llamada HTTP del CollaborationService (reviews-analitica-colaboracion).
 * No prueba componentes visuales, solo la capa de comunicación.
 */
import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { CollaborationService } from './collaboration.service';
import { environment } from '../../environments/environment';

describe('CollaborationService', () => {
  let service: CollaborationService;
  let httpMock: HttpTestingController;
  const API = environment.apiUrl;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [CollaborationService],
    });
    service = TestBed.inject(CollaborationService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  describe('Collaborators', () => {
    it('getCollaborators() GETs /presentations/{id}/collaborators', () => {
      service.getCollaborators(7).subscribe();
      const req = httpMock.expectOne(`${API}/presentations/7/collaborators`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });

    it('addCollaborator() POSTs with user_id body', () => {
      service.addCollaborator(7, 42).subscribe();
      const req = httpMock.expectOne(`${API}/presentations/7/collaborators`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ user_id: 42 });
      req.flush({ user_id: 42, added_at: '2026-01-01' });
    });

    it('removeCollaborator() DELETEs /presentations/{id}/collaborators/{userId}', () => {
      service.removeCollaborator(7, 42).subscribe();
      const req = httpMock.expectOne(`${API}/presentations/7/collaborators/42`);
      expect(req.request.method).toBe('DELETE');
      req.flush({ status: 'removed' });
    });
  });

  describe('Reviews', () => {
    it('getReviews() GETs /presentations/{id}/reviews', () => {
      service.getReviews(7).subscribe();
      const req = httpMock.expectOne(`${API}/presentations/7/reviews`);
      expect(req.request.method).toBe('GET');
      req.flush({ reviews: [], rating_average: null, rating_count: 0 });
    });

    it('upsertReview() POSTs rating and comment', () => {
      service.upsertReview(7, 5, 'great').subscribe();
      const req = httpMock.expectOne(`${API}/presentations/7/reviews`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ rating: 5, comment: 'great' });
      req.flush({});
    });

    it('deleteOwnReview() DELETEs /presentations/{id}/reviews/me', () => {
      service.deleteOwnReview(7).subscribe();
      const req = httpMock.expectOne(`${API}/presentations/7/reviews/me`);
      expect(req.request.method).toBe('DELETE');
      req.flush({ status: 'deleted' });
    });
  });

  describe('Users & directory', () => {
    it('getUsers() GETs /users', () => {
      service.getUsers().subscribe();
      const req = httpMock.expectOne(`${API}/users`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });

    it('getUserDirectory() GETs /users/directory', () => {
      service.getUserDirectory().subscribe();
      const req = httpMock.expectOne(`${API}/users/directory`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });
  });

  describe('Departments', () => {
    it('getDepartments() omits tenant_id param when not provided', () => {
      service.getDepartments().subscribe();
      const req = httpMock.expectOne(`${API}/admin/departments`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });

    it('getDepartments() includes tenant_id when provided', () => {
      service.getDepartments(4).subscribe();
      const req = httpMock.expectOne(`${API}/admin/departments?tenant_id=4`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });

    it('createDepartment() POSTs name and tenant_id', () => {
      service.createDepartment('Sales', 4).subscribe();
      const req = httpMock.expectOne(`${API}/admin/departments`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ name: 'Sales', tenant_id: 4 });
      req.flush({});
    });

    it('deleteDepartment() DELETEs /admin/departments/{id}', () => {
      service.deleteDepartment(9).subscribe();
      const req = httpMock.expectOne(`${API}/admin/departments/9`);
      expect(req.request.method).toBe('DELETE');
      req.flush({ status: 'deleted' });
    });

    it('updateUserDepartment() PATCHes department_id (including null)', () => {
      service.updateUserDepartment(3, null).subscribe();
      const req = httpMock.expectOne(`${API}/users/3/department`);
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body).toEqual({ department_id: null });
      req.flush({});
    });
  });

  describe('Analytics & reports', () => {
    it('getUsageAnalytics() includes tenant_id only when provided', () => {
      service.getUsageAnalytics(4).subscribe();
      const req = httpMock.expectOne(`${API}/admin/analytics/usage?tenant_id=4`);
      expect(req.request.method).toBe('GET');
      req.flush({ users: [] });
    });

    it('getUsageReports() omits tenant_id when not provided', () => {
      service.getUsageReports().subscribe();
      const req = httpMock.expectOne(`${API}/admin/usage-reports`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });
  });

  describe('Moderation', () => {
    it('getAdminReviews() includes status_filter param when provided', () => {
      service.getAdminReviews('flagged').subscribe();
      const req = httpMock.expectOne(`${API}/admin/reviews?status_filter=flagged`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });

    it('getAdminReviews() omits status_filter when not provided', () => {
      service.getAdminReviews().subscribe();
      const req = httpMock.expectOne(`${API}/admin/reviews`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });

    it('updateReviewModeration() PATCHes status', () => {
      service.updateReviewModeration(11, 'hidden').subscribe();
      const req = httpMock.expectOne(`${API}/admin/reviews/11/moderation`);
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body).toEqual({ status: 'hidden' });
      req.flush({});
    });

    it('getModerationBlocklist() GETs the blocklist config', () => {
      service.getModerationBlocklist().subscribe();
      const req = httpMock.expectOne(`${API}/admin/config/review-moderation-blocklist`);
      expect(req.request.method).toBe('GET');
      req.flush({ terms: [] });
    });

    it('updateModerationBlocklist() PATCHes terms', () => {
      service.updateModerationBlocklist(['spam']).subscribe();
      const req = httpMock.expectOne(`${API}/admin/config/review-moderation-blocklist`);
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body).toEqual({ terms: ['spam'] });
      req.flush({ terms: ['spam'] });
    });
  });

  describe('Badges', () => {
    it('getMyBadges() GETs /users/me/badges', () => {
      service.getMyBadges().subscribe();
      const req = httpMock.expectOne(`${API}/users/me/badges`);
      expect(req.request.method).toBe('GET');
      req.flush({ count: 0, current_badge: null, next_badge: null, progress_to_next: null });
    });
  });
});
