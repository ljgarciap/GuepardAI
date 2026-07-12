import { Component, EventEmitter, Input, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  BrandService, PortfolioItem, PromptIntent, PromptMetadata, TemplateMergeHistoryItem,
} from '../../services/brand.service';
import { PromptFavoritesService, PromptFavorite } from '../../services/prompt-favorites.service';
import { ConfirmDialogService } from '../../services/confirm-dialog.service';
import { PromptComposerComponent } from '../generator/prompt-composer/prompt-composer.component';

/**
 * Facilidad de prompts compartida entre Synthesis Studio y Template Merge
 * (docs/designs/biblioteca-prompts-favoritos.md, "compartir con Template Merge").
 * El padre sigue dueño del textarea real — este componente solo decide QUÉ
 * texto/metadata aplicar, vía applyText, con confirmación si hace falta.
 */
@Component({
  selector: 'app-prompt-support',
  standalone: true,
  imports: [CommonModule, FormsModule, PromptComposerComponent],
  templateUrl: './prompt-support.component.html',
  styleUrl: './prompt-support.component.css'
})
export class PromptSupportComponent {
  @Input() mode: 'synthesis' | 'template-merge' = 'synthesis';
  @Input() brandId: number | null = null;
  @Input() currentText = '';
  @Input() currentMetadata: PromptMetadata | null = null;
  /** Permite al padre ocultar las 4 tarjetas (ej. durante generación/resultados)
   * sin desmontar el componente — los modales siguen siendo alcanzables desde
   * fuera vía una template reference variable (ej. el botón "Save as favorite"). */
  @Input() showCards = true;
  @Output() applyText = new EventEmitter<{ text: string; metadata: PromptMetadata | null }>();
  @Output() loadError = new EventEmitter<string>();

  private brandService = inject(BrandService);
  private promptFavoritesService = inject(PromptFavoritesService);
  private confirmDialogService = inject(ConfirmDialogService);

  // --- AYUDA 1: Reutilizar indicación anterior ---
  showReuseModal = false;
  reusablePortfolios: PortfolioItem[] = [];
  reusableMergeJobs: TemplateMergeHistoryItem[] = [];
  loadingReusable = false;

  // --- AYUDA 2: Biblioteca de intenciones ---
  showIntentModal = false;
  promptIntents: PromptIntent[] = [];
  loadingIntents = false;

  // --- AYUDA 3: Compositor guiado + guía ---
  showComposerModal = false;
  composerInitialValues: Partial<PromptMetadata> | null = null;

  // --- AYUDA 4: Prompts favoritos ---
  showFavoritesModal = false;
  favoritesList: PromptFavorite[] = [];
  loadingFavorites = false;

  showSaveFavoriteModal = false;
  saveFavoriteTitle = '';
  savingFavorite = false;
  saveFavoriteError = '';

  /** Emite el texto/metadata solo si el usuario confirma sobreescribir (o no había nada que sobreescribir). */
  private confirmAndApply(text: string, metadata: PromptMetadata | null, onApplied: () => void): void {
    const proceed = () => {
      this.applyText.emit({ text, metadata });
      onApplied();
    };
    if (this.currentText.trim()) {
      this.confirmDialogService.confirm('This will replace your current prompt text. Continue?').subscribe((ok) => {
        if (ok) proceed();
      });
      return;
    }
    proceed();
  }

  // --- AYUDA 1 ---
  openReuseModal(): void {
    this.showReuseModal = true;
    this.loadingReusable = true;
    if (this.mode === 'synthesis') {
      this.brandService.getLibraryPortfolios(this.brandId || undefined, { pageSize: 50 }).subscribe({
        next: (res) => {
          this.reusablePortfolios = (res.items || []).filter(p => p.has_prompt);
          this.loadingReusable = false;
        },
        error: () => { this.loadingReusable = false; }
      });
    } else {
      this.brandService.getTemplateMergeHistory(this.brandId || undefined, { pageSize: 50 }).subscribe({
        next: (res) => {
          this.reusableMergeJobs = res.items || [];
          this.loadingReusable = false;
        },
        error: () => { this.loadingReusable = false; }
      });
    }
  }

  useAsBase(jobId: number): void {
    if (this.mode === 'synthesis') {
      this.brandService.getPortfolioDetail(jobId).subscribe({
        next: (detail) => this.confirmAndApply(detail.prompt, detail.prompt_metadata, () => { this.showReuseModal = false; }),
        error: () => this.loadError.emit('Could not load that presentation as a base.')
      });
    } else {
      this.brandService.getTemplateMergeJobDetail(jobId).subscribe({
        next: (detail) => this.confirmAndApply(detail.prompt, null, () => { this.showReuseModal = false; }),
        error: () => this.loadError.emit('Could not load that merge job as a base.')
      });
    }
  }

  // --- AYUDA 2 ---
  openIntentModal(): void {
    this.showIntentModal = true;
    this.loadingIntents = true;
    this.brandService.getPromptIntents().subscribe({
      next: (res) => {
        this.promptIntents = res || [];
        this.loadingIntents = false;
      },
      error: () => { this.loadingIntents = false; }
    });
  }

  selectIntent(intent: PromptIntent): void {
    this.composerInitialValues = {
      objective: intent.label,
      tone: intent.expected_tone,
      story: intent.narrative_style,
      slide_type: this.mode === 'synthesis' ? (intent.preferred_layouts?.[0] || '') : '',
    };
    this.showIntentModal = false;
    this.showComposerModal = true;
  }

  // --- AYUDA 3 ---
  openComposerModal(): void {
    this.showComposerModal = true;
  }

  onComposerInsert(payload: { text: string; metadata: PromptMetadata }): void {
    this.confirmAndApply(payload.text, payload.metadata, () => { this.showComposerModal = false; });
  }

  // --- AYUDA 4 ---
  openFavoritesModal(): void {
    this.showFavoritesModal = true;
    this.loadingFavorites = true;
    this.promptFavoritesService.listFavorites().subscribe({
      next: (res) => {
        this.favoritesList = res || [];
        this.loadingFavorites = false;
      },
      error: () => { this.loadingFavorites = false; }
    });
  }

  useFavorite(fav: PromptFavorite): void {
    this.confirmAndApply(fav.prompt_text, fav.prompt_metadata, () => { this.showFavoritesModal = false; });
  }

  openSaveFavoriteModal(): void {
    this.saveFavoriteTitle = '';
    this.saveFavoriteError = '';
    this.showSaveFavoriteModal = true;
  }

  confirmSaveFavorite(): void {
    if (!this.saveFavoriteTitle.trim()) return;
    this.savingFavorite = true;
    this.saveFavoriteError = '';
    this.promptFavoritesService.createFavorite({
      title: this.saveFavoriteTitle.trim(),
      prompt_text: this.currentText,
      prompt_metadata: this.currentMetadata,
    }).subscribe({
      next: () => {
        this.savingFavorite = false;
        this.showSaveFavoriteModal = false;
      },
      error: () => {
        this.savingFavorite = false;
        this.saveFavoriteError = 'Could not save this favorite. Please try again.';
      }
    });
  }
}
