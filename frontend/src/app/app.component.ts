import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { SidebarComponent } from './components/layout/sidebar/sidebar.component';
import { ConfirmModalComponent } from './components/shared/confirm-modal/confirm-modal.component';
import { ThemeService } from './services/theme.service';

const SHELL_LESS_ROUTES = ['/login', '/register', '/tos'];

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, SidebarComponent, ConfirmModalComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  title = 'frontend';
  readonly showShell = signal(true);

  constructor(private themeService: ThemeService, private router: Router) {
    this.showShell.set(!SHELL_LESS_ROUTES.includes(this.router.url.split('?')[0]));
    this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => {
        const path = event.urlAfterRedirects.split('?')[0];
        this.showShell.set(!SHELL_LESS_ROUTES.includes(path));
      });
  }
}
