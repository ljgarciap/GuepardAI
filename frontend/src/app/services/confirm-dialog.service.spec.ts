import { TestBed } from '@angular/core/testing';
import { ConfirmDialogService } from './confirm-dialog.service';

describe('ConfirmDialogService', () => {
  let service: ConfirmDialogService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [ConfirmDialogService] });
    service = TestBed.inject(ConfirmDialogService);
  });

  it('starts hidden', (done) => {
    service.state$.subscribe((state) => {
      expect(state.visible).toBeFalse();
      done();
    });
  });

  it('confirm() shows the modal with the given message', () => {
    service.confirm('Are you sure?').subscribe();
    let latest: { visible: boolean; message: string } | undefined;
    service.state$.subscribe((state) => (latest = state));

    expect(latest?.visible).toBeTrue();
    expect(latest?.message).toBe('Are you sure?');
  });

  it('respond(true) resolves the observable with true and hides the modal', (done) => {
    service.confirm('Delete this?').subscribe((result) => {
      expect(result).toBeTrue();
      done();
    });
    service.respond(true);
  });

  it('respond(false) resolves the observable with false and hides the modal', (done) => {
    service.confirm('Delete this?').subscribe((result) => {
      expect(result).toBeFalse();
      done();
    });
    service.respond(false);

    service.state$.subscribe((state) => expect(state.visible).toBeFalse());
  });
});
