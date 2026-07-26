import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, NgForm } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-account',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './account.component.html',
  styleUrl: './account.component.css'
})
export class AccountComponent {
  private authService = inject(AuthService);

  currentPassword = '';
  newPassword = '';
  confirmPassword = '';
  isSubmitting = false;
  errorMessage: string | null = null;
  successMessage: string | null = null;

  get userEmail(): string | null {
    return this.authService.currentUser?.email ?? null;
  }

  get passwordsMismatch(): boolean {
    // NgForm.resetForm() sets bound ngModel values to null (not ''), so this
    // must stay null-safe even though the fields are typed as string.
    return !!this.confirmPassword && this.newPassword !== this.confirmPassword;
  }

  submit(form: NgForm): void {
    if (form.invalid || this.passwordsMismatch || this.isSubmitting) return;

    this.isSubmitting = true;
    this.errorMessage = null;
    this.successMessage = null;

    this.authService.changePassword(this.currentPassword, this.newPassword).subscribe({
      next: () => {
        this.isSubmitting = false;
        this.successMessage = 'Your password has been changed.';
        form.resetForm({ currentPassword: '', newPassword: '', confirmPassword: '' });
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting = false;
        this.errorMessage = err.status === 400
          ? 'Current password is incorrect.'
          : 'Could not change your password. Please try again.';
      },
    });
  }
}
