import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { SidebarComponent } from './sidebar.component';
import { BrandService } from '../../../services/brand.service';
import { AuthService } from '../../../services/auth.service';
import { CollaborationService, MyBadges } from '../../../services/collaboration.service';

describe('SidebarComponent — badge widget', () => {
  let fixture: ComponentFixture<SidebarComponent>;
  let component: SidebarComponent;
  let collabSpy: jasmine.SpyObj<CollaborationService>;
  let authStub: { currentUser$: any; currentUser: any };

  beforeEach(() => {
    collabSpy = jasmine.createSpyObj('CollaborationService', ['getMyBadges']);
  });

  function setup(user: { id: number; email: string; role: string } | null) {
    authStub = { currentUser$: of(user), currentUser: user };

    TestBed.configureTestingModule({
      imports: [SidebarComponent],
      providers: [
        provideRouter([]),
        { provide: BrandService, useValue: jasmine.createSpyObj('BrandService', ['resetDatabase']) },
        { provide: AuthService, useValue: authStub },
        { provide: CollaborationService, useValue: collabSpy },
      ],
    });
    fixture = TestBed.createComponent(SidebarComponent);
    component = fixture.componentInstance;
  }

  it('loads badges when a user is logged in', () => {
    const badges: MyBadges = { count: 7, current_badge: { threshold: 5, label: 'Starter' }, next_badge: { threshold: 10, label: 'Expert' }, progress_to_next: 0.4 };
    collabSpy.getMyBadges.and.returnValue(of(badges));
    setup({ id: 1, email: 'user@example.com', role: 'cliente' });

    fixture.detectChanges(); // ngOnInit

    expect(collabSpy.getMyBadges).toHaveBeenCalled();
    expect(component.myBadges).toEqual(badges);
  });

  it('does not call getMyBadges when there is no logged-in user', () => {
    setup(null);
    fixture.detectChanges();

    expect(collabSpy.getMyBadges).not.toHaveBeenCalled();
    expect(component.myBadges).toBeNull();
  });

  it('sets myBadges to null if the request fails, without throwing', () => {
    collabSpy.getMyBadges.and.returnValue(throwError(() => new Error('network error')));
    setup({ id: 1, email: 'user@example.com', role: 'cliente' });

    expect(() => fixture.detectChanges()).not.toThrow();
    expect(component.myBadges).toBeNull();
  });

  describe('role getters', () => {
    it('isAdminOrSuperadmin is true for admin', () => {
      setup({ id: 1, email: 'a@example.com', role: 'admin' });
      expect(component.isAdminOrSuperadmin).toBeTrue();
    });

    it('isAdminOrSuperadmin is true for superadmin', () => {
      setup({ id: 1, email: 'a@example.com', role: 'superadmin' });
      expect(component.isAdminOrSuperadmin).toBeTrue();
    });

    it('isAdminOrSuperadmin is false for cliente', () => {
      setup({ id: 1, email: 'a@example.com', role: 'cliente' });
      expect(component.isAdminOrSuperadmin).toBeFalse();
    });

    it('isSuperadmin is true only for superadmin', () => {
      setup({ id: 1, email: 'a@example.com', role: 'admin' });
      expect(component.isSuperadmin).toBeFalse();
    });
  });
});
