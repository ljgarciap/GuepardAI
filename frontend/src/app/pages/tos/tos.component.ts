import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { TosService, TosStatus } from '../../services/tos.service';
import { AuthService } from '../../services/auth.service';
import { ConfirmDialogService } from '../../services/confirm-dialog.service';

@Component({
  selector: 'app-tos',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './tos.component.html',
  styleUrl: './tos.component.css'
})
export class TosComponent implements OnInit {
  private tosService = inject(TosService);
  private authService = inject(AuthService);
  private confirmDialogService = inject(ConfirmDialogService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  status: TosStatus | null = null;
  isLoading = true;
  isSubmitting = false;
  errorMessage: string | null = null;

  ngOnInit(): void {
    this.tosService.fetchStatus().subscribe({
      next: (s) => { this.status = s; this.isLoading = false; },
      error: () => { this.isLoading = false; this.errorMessage = 'Could not load Terms of Service status.'; },
    });
  }

  get userEmail(): string | null {
    return this.authService.currentUser?.email ?? null;
  }

  accept(): void {
    if (this.isSubmitting) return;
    this.isSubmitting = true;
    this.errorMessage = null;
    this.tosService.accept().subscribe({
      next: (s) => {
        this.status = s;
        this.isSubmitting = false;
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') || '/';
        this.router.navigateByUrl(returnUrl);
      },
      error: () => {
        this.isSubmitting = false;
        this.errorMessage = 'Could not record your acceptance. Please try again.';
      },
    });
  }

  reject(): void {
    if (this.isSubmitting) return;
    this.confirmDialogService.confirm(
      'Rejecting the Terms of Service will immediately lock you out of everything you\'ve generated in Guepard AI until you accept them again. Continue?'
    ).subscribe((ok) => {
      if (!ok) return;
      this.isSubmitting = true;
      this.errorMessage = null;
      this.tosService.reject().subscribe({
        next: (s) => { this.status = s; this.isSubmitting = false; },
        error: () => {
          this.isSubmitting = false;
          this.errorMessage = 'Could not record your rejection. Please try again.';
        },
      });
    });
  }

  logout(): void {
    this.authService.logout();
  }
}
