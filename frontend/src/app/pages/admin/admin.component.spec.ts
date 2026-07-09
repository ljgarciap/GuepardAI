import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { AdminComponent } from './admin.component';
import { CollaborationService } from '../../services/collaboration.service';
import { AuthService } from '../../services/auth.service';

describe('AdminComponent', () => {
  let fixture: ComponentFixture<AdminComponent>;
  let component: AdminComponent;
  let collabSpy: jasmine.SpyObj<CollaborationService>;
  let authStub: { currentUser: { role: string } | null };

  function setup(role: string) {
    authStub = { currentUser: { role } };
    collabSpy = jasmine.createSpyObj('CollaborationService', [
      'getDepartments', 'getUsers', 'createDepartment', 'deleteDepartment', 'updateUserDepartment',
      'getAdminReviews', 'updateReviewModeration', 'getModerationBlocklist', 'updateModerationBlocklist',
      'getUsageAnalytics', 'getUsageReports',
    ]);
    collabSpy.getDepartments.and.returnValue(of([]));
    collabSpy.getUsers.and.returnValue(of([]));
    collabSpy.getAdminReviews.and.returnValue(of([]));
    collabSpy.getModerationBlocklist.and.returnValue(of({ terms: [] }));
    collabSpy.getUsageAnalytics.and.returnValue(of({ users: [] }));
    collabSpy.getUsageReports.and.returnValue(of([]));

    TestBed.configureTestingModule({
      imports: [AdminComponent],
      providers: [
        { provide: CollaborationService, useValue: collabSpy },
        { provide: AuthService, useValue: authStub },
      ],
    });
    fixture = TestBed.createComponent(AdminComponent);
    component = fixture.componentInstance;
    fixture.detectChanges(); // ngOnInit -> setTab('departments')
  }

  describe('as tenant admin', () => {
    beforeEach(() => setup('admin'));

    it('loads departments and users on init (default tab)', () => {
      expect(component.activeTab).toBe('departments');
      expect(collabSpy.getDepartments).toHaveBeenCalled();
      expect(collabSpy.getUsers).toHaveBeenCalled();
    });

    it('isSuperadmin is false', () => {
      expect(component.isSuperadmin).toBeFalse();
    });

    it('switching to moderation tab loads reviews but NOT the blocklist for a non-superadmin', () => {
      component.setTab('moderation');
      expect(collabSpy.getAdminReviews).toHaveBeenCalledWith('flagged');
      expect(collabSpy.getModerationBlocklist).not.toHaveBeenCalled();
    });

    it('switching to analytics tab loads usage analytics', () => {
      component.setTab('analytics');
      expect(collabSpy.getUsageAnalytics).toHaveBeenCalled();
    });

    it('switching to reports tab loads usage reports', () => {
      component.setTab('reports');
      expect(collabSpy.getUsageReports).toHaveBeenCalled();
    });

    it('createDepartment() does nothing for a blank name', () => {
      component.newDepartmentName = '   ';
      component.createDepartment();
      expect(collabSpy.createDepartment).not.toHaveBeenCalled();
    });

    it('createDepartment() calls the service, clears the input, and reloads on success', () => {
      collabSpy.createDepartment.and.returnValue(of({ id: 1, tenant_id: 4, name: 'Sales' }));
      component.newDepartmentName = 'Sales';
      component.createDepartment();

      expect(collabSpy.createDepartment).toHaveBeenCalledWith('Sales', undefined);
      expect(component.newDepartmentName).toBe('');
      expect(collabSpy.getDepartments).toHaveBeenCalledTimes(2); // init + reload
    });

    it('createDepartment() surfaces the backend error message', () => {
      collabSpy.createDepartment.and.returnValue(
        // @ts-ignore — simulamos un error HTTP
        { subscribe: (handlers: any) => handlers.error({ error: { detail: 'Department name already exists for this tenant' } }) }
      );
      component.newDepartmentName = 'Sales';
      component.createDepartment();

      expect(component.departmentError).toBe('Department name already exists for this tenant');
    });

    it('deleteDepartment() calls the service and reloads', () => {
      collabSpy.deleteDepartment.and.returnValue(of({ status: 'deleted' }));
      component.deleteDepartment({ id: 9, tenant_id: 4, name: 'Old' });

      expect(collabSpy.deleteDepartment).toHaveBeenCalledWith(9);
      expect(collabSpy.getDepartments).toHaveBeenCalledTimes(2);
    });

    it('assignDepartment() does nothing without a selected user', () => {
      component.assignUserId = null;
      component.assignDepartment();
      expect(collabSpy.updateUserDepartment).not.toHaveBeenCalled();
    });

    it('assignDepartment() calls the service with the selected user and department', () => {
      collabSpy.updateUserDepartment.and.returnValue(of({ id: 3, email: 'a@b.com', role: 'cliente', tenant_id: 4, is_active: 1, department_id: 9 }));
      component.assignUserId = 3;
      component.assignDepartmentId = 9;
      component.assignDepartment();

      expect(collabSpy.updateUserDepartment).toHaveBeenCalledWith(3, 9);
    });

    it('setModerationStatus() calls the service and reloads the review list', () => {
      component.setTab('moderation');
      collabSpy.getAdminReviews.calls.reset();
      collabSpy.updateReviewModeration.and.returnValue(of({} as any));

      component.setModerationStatus({ id: 5 } as any, 'hidden');

      expect(collabSpy.updateReviewModeration).toHaveBeenCalledWith(5, 'hidden');
      expect(collabSpy.getAdminReviews).toHaveBeenCalled();
    });

    it('formatMinutes() rounds seconds to whole minutes', () => {
      expect(component.formatMinutes(125)).toBe('2 min');
      expect(component.formatMinutes(0)).toBe('0 min');
    });
  });

  describe('as superadmin', () => {
    beforeEach(() => setup('superadmin'));

    it('isSuperadmin is true', () => {
      expect(component.isSuperadmin).toBeTrue();
    });

    it('switching to moderation tab also loads the blocklist', () => {
      component.setTab('moderation');
      expect(collabSpy.getModerationBlocklist).toHaveBeenCalled();
    });

    it('saveBlocklist() splits comma-separated text into a trimmed terms array', () => {
      collabSpy.updateModerationBlocklist.and.returnValue(of({ terms: ['spam', 'scam'] }));
      component.blocklistText = ' spam ,  scam ,, ';

      component.saveBlocklist();

      expect(collabSpy.updateModerationBlocklist).toHaveBeenCalledWith(['spam', 'scam']);
    });
  });
});
