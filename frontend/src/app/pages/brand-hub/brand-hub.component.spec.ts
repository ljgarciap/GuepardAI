import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { BrandHubComponent } from './brand-hub.component';
import { BrandService } from '../../services/brand.service';
import { AuthService } from '../../services/auth.service';
import { ConfirmDialogService } from '../../services/confirm-dialog.service';
import { CollaborationService } from '../../services/collaboration.service';

describe('BrandHubComponent — tenant scoping (superadmin brand registry gap)', () => {
  let fixture: ComponentFixture<BrandHubComponent>;
  let component: BrandHubComponent;
  let brandSpy: jasmine.SpyObj<BrandService>;
  let collabSpy: jasmine.SpyObj<CollaborationService>;
  let authStub: { currentUser: { role: string } | null };

  function setup(role: string) {
    authStub = { currentUser: { role } };
    brandSpy = jasmine.createSpyObj('BrandService', ['getBrands', 'createBrand', 'getFooters']);
    brandSpy.getBrands.and.returnValue(of([]));
    brandSpy.getFooters.and.returnValue(of({ is_footer_enabled: true, footers: [] }));
    collabSpy = jasmine.createSpyObj('CollaborationService', ['getTenants']);
    collabSpy.getTenants.and.returnValue(of([]));

    TestBed.configureTestingModule({
      imports: [BrandHubComponent],
      providers: [
        { provide: BrandService, useValue: brandSpy },
        { provide: AuthService, useValue: authStub },
        { provide: ConfirmDialogService, useValue: jasmine.createSpyObj('ConfirmDialogService', ['confirm']) },
        { provide: CollaborationService, useValue: collabSpy },
      ],
    });
    fixture = TestBed.createComponent(BrandHubComponent);
    component = fixture.componentInstance;
    fixture.detectChanges(); // ngOnInit
  }

  describe('as tenant admin', () => {
    beforeEach(() => setup('admin'));

    it('does not load tenants (no scoping needed — always own tenant)', () => {
      expect(collabSpy.getTenants).not.toHaveBeenCalled();
    });

    it('loadBrands() calls the service without a tenant filter', () => {
      expect(brandSpy.getBrands).toHaveBeenCalledWith(undefined);
    });

    it('createNewBrand() does not require a tenant selection', () => {
      brandSpy.createBrand.and.returnValue(of({ id: 1, name: 'Acme' }));
      component.newBrandName = 'Acme';
      component.createNewBrand();
      expect(brandSpy.createBrand).toHaveBeenCalledWith('Acme', undefined, undefined, undefined, undefined);
    });
  });

  describe('as superadmin', () => {
    beforeEach(() => setup('superadmin'));

    it('loads tenants on init', () => {
      expect(collabSpy.getTenants).toHaveBeenCalled();
    });

    it('createNewBrand() is a no-op without a tenant scope selected', () => {
      spyOn(window, 'alert');
      component.selectedTenantId = null;
      component.newBrandName = 'Acme';
      component.createNewBrand();
      expect(brandSpy.createBrand).not.toHaveBeenCalled();
      expect(window.alert).toHaveBeenCalled();
    });

    it('createNewBrand() scopes to the selected tenant once one is chosen', () => {
      brandSpy.createBrand.and.returnValue(of({ id: 2, name: 'Acme', tenant_id: 5 }));
      component.selectedTenantId = 5;
      component.newBrandName = 'Acme';
      component.createNewBrand();
      expect(brandSpy.createBrand).toHaveBeenCalledWith('Acme', undefined, undefined, undefined, 5);
    });

    it('onTenantScopeChange() reloads brands scoped to the new tenant', () => {
      brandSpy.getBrands.calls.reset();
      component.selectedTenantId = 7;
      component.onTenantScopeChange();
      expect(brandSpy.getBrands).toHaveBeenCalledWith(7);
    });
  });
});
