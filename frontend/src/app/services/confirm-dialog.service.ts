import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

export interface ConfirmDialogState {
  visible: boolean;
  message: string;
}

@Injectable({ providedIn: 'root' })
export class ConfirmDialogService {
  private stateSubject = new BehaviorSubject<ConfirmDialogState>({ visible: false, message: '' });
  state$ = this.stateSubject.asObservable();

  private pendingResolve: ((result: boolean) => void) | null = null;

  /** Reemplazo estilizado de window.confirm(). Resuelve true/false según el botón elegido. */
  confirm(message: string): Observable<boolean> {
    return new Observable<boolean>((subscriber) => {
      this.stateSubject.next({ visible: true, message });
      this.pendingResolve = (result: boolean) => {
        subscriber.next(result);
        subscriber.complete();
      };
    });
  }

  respond(result: boolean): void {
    this.stateSubject.next({ visible: false, message: '' });
    if (this.pendingResolve) {
      this.pendingResolve(result);
      this.pendingResolve = null;
    }
  }
}
