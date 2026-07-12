import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { ConfirmModalComponent } from './confirm-modal.component';
import { ConfirmDialogService } from '../../../services/confirm-dialog.service';

describe('ConfirmModalComponent', () => {
  let fixture: ComponentFixture<ConfirmModalComponent>;
  let service: ConfirmDialogService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmModalComponent],
      providers: [ConfirmDialogService],
    }).compileComponents();

    fixture = TestBed.createComponent(ConfirmModalComponent);
    service = TestBed.inject(ConfirmDialogService);
    fixture.detectChanges();
  });

  it('is hidden until confirm() is called', () => {
    expect(fixture.nativeElement.querySelector('.feedback-modal-overlay')).toBeNull();
  });

  it('shows the message once confirm() is called', () => {
    service.confirm('Delete this favorite?').subscribe();
    fixture.detectChanges();

    const question = fixture.nativeElement.querySelector('.question');
    expect(question.textContent).toContain('Delete this favorite?');
  });

  it('clicking CONTINUE resolves the pending confirm() with true and hides the modal', () => {
    let result: boolean | undefined;
    service.confirm('Proceed?').subscribe((r) => (result = r));
    fixture.detectChanges();

    const continueBtn = fixture.debugElement.query(By.css('.btn-primary-enterprise'));
    continueBtn.nativeElement.click();
    fixture.detectChanges();

    expect(result).toBeTrue();
    expect(fixture.nativeElement.querySelector('.feedback-modal-overlay')).toBeNull();
  });

  it('clicking CANCEL resolves the pending confirm() with false', () => {
    let result: boolean | undefined;
    service.confirm('Proceed?').subscribe((r) => (result = r));
    fixture.detectChanges();

    const cancelBtn = fixture.debugElement.query(By.css('.btn-secondary'));
    cancelBtn.nativeElement.click();
    fixture.detectChanges();

    expect(result).toBeFalse();
  });
});
