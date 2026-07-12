import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ConfirmDialogService } from '../../../services/confirm-dialog.service';

@Component({
  selector: 'app-confirm-modal',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './confirm-modal.component.html',
  styleUrl: './confirm-modal.component.css'
})
export class ConfirmModalComponent {
  private confirmDialogService = inject(ConfirmDialogService);
  state$ = this.confirmDialogService.state$;

  respond(result: boolean): void {
    this.confirmDialogService.respond(result);
  }
}
