import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { BrandService } from '../../../services/brand.service';
import { ThemeService } from '../../../services/theme.service';
import { AuthService } from '../../../services/auth.service';
import { CollaborationService, MyBadges } from '../../../services/collaboration.service';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.css'
})
export class SidebarComponent implements OnInit {
  myBadges: MyBadges | null = null;

  constructor(
    private brandService: BrandService,
    private collaborationService: CollaborationService,
    public themeService: ThemeService,
    public authService: AuthService
  ) {}

  ngOnInit() {
    this.authService.currentUser$.subscribe(user => {
      if (user) {
        this.collaborationService.getMyBadges().subscribe({
          next: (res) => this.myBadges = res,
          error: () => { this.myBadges = null; }
        });
      } else {
        this.myBadges = null;
      }
    });
  }

  get logoSrc(): string {
    return this.themeService.theme() === 'dark' ? 'logo-dark.png' : 'logo-light.png';
  }

  get userInitial(): string {
    const email = this.authService.currentUser?.email;
    return email ? email.charAt(0).toUpperCase() : '?';
  }

  get isSuperadmin(): boolean {
    return this.authService.currentUser?.role === 'superadmin';
  }

  get isAdminOrSuperadmin(): boolean {
    const role = this.authService.currentUser?.role;
    return role === 'admin' || role === 'superadmin';
  }

  logout(): void {
    this.authService.logout();
  }

  resetSystem(): void {
    if (confirm('Are you sure you want to COMPLETELY wipe the database and all uploaded files? This action cannot be undone.')) {
      this.brandService.resetDatabase().subscribe({
        next: (res) => {
          alert('System successfully wiped and reset.');
          window.location.reload();
        },
        error: (err) => {
          console.error(err);
          alert('Error while trying to reset the system.');
        }
      });
    }
  }
}
