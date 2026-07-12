import { Component, inject, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, Subscription, debounceTime, distinctUntilChanged } from 'rxjs';
import { BrandService, PortfolioItem } from '../../services/brand.service';
import { AuthService } from '../../services/auth.service';
import { CollaborationService, Collaborator, Review } from '../../services/collaboration.service';
import { PromptFavoritesService, PromptFavorite } from '../../services/prompt-favorites.service';
import { environment } from '../../../environments/environment';
import { triggerBlobDownload } from '../../utils/download.util';

@Component({
  selector: 'app-asset-library',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './asset-library.component.html',
  styleUrl: './asset-library.component.css'
})
export class AssetLibraryComponent implements OnInit, OnDestroy {
  private brandService = inject(BrandService);
  private collaborationService = inject(CollaborationService);
  private promptFavoritesService = inject(PromptFavoritesService);
  private authService = inject(AuthService);
  baseUrl = environment.baseUrl;

  brands: any[] = [];
  selectedBrandId: number | null = null;
  activeTab: 'images' | 'blueprints' | 'knowledge' | 'portfolios' | 'prompts' = 'images';

  images: any[] = [];
  blueprints: any[] = [];
  knowledge: any[] = [];
  portfolios: PortfolioItem[] = [];

  // --- PROMPT FAVORITES (biblioteca-prompts-favoritos) ---
  favorites: PromptFavorite[] = [];
  editingFavoriteId: number | null = null;
  editFavoriteTitle = '';
  editFavoritePromptText = '';

  // --- PORTFOLIO MANAGEMENT (búsqueda, paginación, rename, delete) ---
  portfolioSearch = '';
  portfolioDateFrom = '';
  portfolioDateTo = '';
  portfolioPage = 1;
  portfolioPageSize = 12;
  portfolioTotal = 0;

  renamingJobId: number | null = null;
  renameValue = '';

  deleteTarget: PortfolioItem | null = null;
  showDeleteModal = false;

  private portfolioSearch$ = new Subject<string>();
  private searchSub?: Subscription;

  selectedAsset: any = null;
  showModal = false;

  // --- REVIEW SYSTEM ---
  showRatingModal = false;
  ratingJobId: number | null = null;
  selectedRating = 0;
  feedbackComment = '';

  selectedComment = '';
  showCommentModal = false;

  // --- PRESENTATION DETAIL: reviews + collaborators (reviews-analitica-colaboracion) ---
  showDetailModal = false;
  detailJob: PortfolioItem | null = null;
  detailReviews: Review[] = [];
  detailRatingAverage: number | null = null;
  detailRatingCount = 0;
  detailCollaborators: Collaborator[] = [];
  detailLoading = false;
  detailError = '';

  myReviewRating = 0;
  myReviewComment = '';

  userDirectory: { id: number; email: string }[] = [];
  selectedCollaboratorUserId: number | null = null;
  collaboratorError = '';

  get currentUserId(): number | null {
    return this.authService.currentUser?.id ?? null;
  }

  ngOnInit() {
    this.loadBrands();
    this.searchSub = this.portfolioSearch$
      .pipe(debounceTime(300), distinctUntilChanged())
      .subscribe(() => {
        this.portfolioPage = 1;
        this.loadPortfolios();
      });
    this.refreshLibrary();
  }

  ngOnDestroy() {
    this.searchSub?.unsubscribe();
  }

  loadBrands() {
    this.brandService.getBrands().subscribe({
      next: (res) => this.brands = res,
      error: (err) => console.error('Error loading brands:', err)
    });
  }

  setTab(tab: 'images' | 'blueprints' | 'knowledge' | 'portfolios' | 'prompts') {
    this.activeTab = tab;
    this.refreshLibrary();
  }

  onBrandChange() {
    this.refreshLibrary();
  }

  openDetail(asset: any) {
    this.selectedAsset = asset;
    this.showModal = true;
  }

  closeDetail() {
    this.showModal = false;
    this.selectedAsset = null;
  }

  refreshLibrary() {
    const bId = this.selectedBrandId || undefined;

    if (this.activeTab === 'images') {
      this.brandService.getLibraryImages(bId).subscribe(res => this.images = res);
    } else if (this.activeTab === 'blueprints') {
      this.brandService.getLibraryBlueprints(bId).subscribe(res => this.blueprints = res);
    } else if (this.activeTab === 'knowledge') {
      this.brandService.getLibraryKnowledge(bId).subscribe(res => this.knowledge = res);
    } else if (this.activeTab === 'portfolios') {
      this.loadPortfolios();
    } else if (this.activeTab === 'prompts') {
      this.loadFavorites();
    }
  }

  // --- PORTFOLIO MANAGEMENT ---

  loadPortfolios() {
    const bId = this.selectedBrandId || undefined;
    this.brandService.getLibraryPortfolios(bId, {
      search: this.portfolioSearch,
      dateFrom: this.portfolioDateFrom || undefined,
      dateTo: this.portfolioDateTo || undefined,
      page: this.portfolioPage,
      pageSize: this.portfolioPageSize
    }).subscribe({
      next: (res) => {
        this.portfolios = res.items;
        this.portfolioTotal = res.total;
        this.portfolioPage = res.page;
      },
      error: (err) => console.error('[AssetLibrary] Error loading portfolios:', err)
    });
  }

  onPortfolioSearchChange(value: string) {
    this.portfolioSearch$.next(value);
  }

  onPortfolioDateChange() {
    this.portfolioPage = 1;
    this.loadPortfolios();
  }

  clearPortfolioFilters() {
    this.portfolioSearch = '';
    this.portfolioDateFrom = '';
    this.portfolioDateTo = '';
    this.portfolioPage = 1;
    this.loadPortfolios();
  }

  get portfolioTotalPages(): number {
    return Math.max(1, Math.ceil(this.portfolioTotal / this.portfolioPageSize));
  }

  goToPortfolioPage(page: number) {
    if (page < 1 || page > this.portfolioTotalPages || page === this.portfolioPage) return;
    this.portfolioPage = page;
    this.loadPortfolios();
  }

  startRename(p: PortfolioItem) {
    this.renamingJobId = p.id;
    this.renameValue = p.display_name;
  }

  cancelRename() {
    this.renamingJobId = null;
    this.renameValue = '';
  }

  confirmRename() {
    const name = this.renameValue.trim();
    if (!this.renamingJobId || !name || name.length > 120) return;

    this.brandService.renamePortfolio(this.renamingJobId, name).subscribe({
      next: (res) => {
        const item = this.portfolios.find(p => p.id === res.id);
        if (item) item.display_name = res.display_name;
        this.cancelRename();
      },
      error: (err) => {
        console.error('[AssetLibrary] Error renaming portfolio:', err);
        this.cancelRename();
        this.loadPortfolios();
      }
    });
  }

  askDeletePortfolio(p: PortfolioItem) {
    this.deleteTarget = p;
    this.showDeleteModal = true;
  }

  cancelDeletePortfolio() {
    this.deleteTarget = null;
    this.showDeleteModal = false;
  }

  confirmDeletePortfolio() {
    if (!this.deleteTarget) return;
    const targetId = this.deleteTarget.id;

    this.brandService.deletePortfolio(targetId).subscribe({
      next: () => {
        this.cancelDeletePortfolio();
        // Si era el último ítem de la página y no es la primera, retroceder
        if (this.portfolios.length === 1 && this.portfolioPage > 1) {
          this.portfolioPage--;
        }
        this.loadPortfolios();
      },
      error: (err) => {
        console.error('[AssetLibrary] Error deleting portfolio:', err);
        this.cancelDeletePortfolio();
        this.loadPortfolios();
      }
    });
  }

  downloadPortfolio(p: PortfolioItem) {
    this.brandService.downloadPortfolio(p.id).subscribe({
      next: (blob) => triggerBlobDownload(blob, p.filename),
      error: (err) => console.error('[AssetLibrary] Error downloading portfolio:', err)
    });
  }

  // --- PROMPT FAVORITES (biblioteca-prompts-favoritos) ---

  loadFavorites() {
    this.promptFavoritesService.listFavorites().subscribe({
      next: (res) => this.favorites = res,
      error: (err) => console.error('[AssetLibrary] Error loading favorites:', err)
    });
  }

  startEditFavorite(fav: PromptFavorite) {
    this.editingFavoriteId = fav.id;
    this.editFavoriteTitle = fav.title;
    this.editFavoritePromptText = fav.prompt_text;
  }

  cancelEditFavorite() {
    this.editingFavoriteId = null;
    this.editFavoriteTitle = '';
    this.editFavoritePromptText = '';
  }

  confirmEditFavorite() {
    const title = this.editFavoriteTitle.trim();
    const promptText = this.editFavoritePromptText.trim();
    if (!this.editingFavoriteId || !title || !promptText) return;

    this.promptFavoritesService.updateFavorite(this.editingFavoriteId, {
      title, prompt_text: promptText,
    }).subscribe({
      next: (updated) => {
        const item = this.favorites.find(f => f.id === updated.id);
        if (item) { item.title = updated.title; item.prompt_text = updated.prompt_text; }
        this.cancelEditFavorite();
      },
      error: (err) => console.error('[AssetLibrary] Error updating favorite:', err)
    });
  }

  deleteFavorite(fav: PromptFavorite) {
    if (!confirm(`Delete favorite "${fav.title}"? This cannot be undone.`)) return;

    this.promptFavoritesService.deleteFavorite(fav.id).subscribe({
      next: () => { this.favorites = this.favorites.filter(f => f.id !== fav.id); },
      error: (err) => console.error('[AssetLibrary] Error deleting favorite:', err)
    });
  }

  openRatingModal(jobId: number) {
    this.ratingJobId = jobId;
    this.selectedRating = 0;
    this.feedbackComment = '';
    this.showRatingModal = true;
  }

  selectRating(rating: number) {
    this.selectedRating = rating;
  }

  submitFeedback() {
    if (!this.ratingJobId || this.selectedRating === 0) return;

    this.brandService.submitFeedback(this.ratingJobId, this.selectedRating, this.feedbackComment).subscribe({
      next: (res) => {
        console.log("[AssetLibrary] Feedback submitted successfully:", res);
        this.showRatingModal = false;
        this.refreshLibrary();
      },
      error: (err) => {
        console.error("[AssetLibrary] Error submitting feedback:", err);
        this.showRatingModal = false;
      }
    });
  }

  viewComment(comment: string) {
    this.selectedComment = comment;
    this.showCommentModal = true;
  }

  closeCommentModal() {
    this.showCommentModal = false;
    this.selectedComment = '';
  }

  // --- PRESENTATION DETAIL: reviews + collaborators ---

  openDetailModal(p: PortfolioItem) {
    this.detailJob = p;
    this.showDetailModal = true;
    this.detailError = '';
    this.collaboratorError = '';
    this.selectedCollaboratorUserId = null;
    this.loadDetailReviews();
    this.loadDetailCollaborators();
    this.loadUserDirectory();
  }

  closeDetailModal() {
    this.showDetailModal = false;
    this.detailJob = null;
    this.detailReviews = [];
    this.detailCollaborators = [];
    this.myReviewRating = 0;
    this.myReviewComment = '';
  }

  private loadDetailReviews() {
    if (!this.detailJob) return;
    this.detailLoading = true;
    this.collaborationService.getReviews(this.detailJob.id).subscribe({
      next: (res) => {
        this.detailReviews = res.reviews;
        this.detailRatingAverage = res.rating_average;
        this.detailRatingCount = res.rating_count;
        this.detailLoading = false;
        const mine = res.reviews.find(r => r.user_id === this.currentUserId);
        if (mine) {
          this.myReviewRating = mine.rating;
          this.myReviewComment = mine.comment || '';
        }
      },
      error: () => { this.detailLoading = false; }
    });
  }

  private loadDetailCollaborators() {
    if (!this.detailJob) return;
    this.collaborationService.getCollaborators(this.detailJob.id).subscribe({
      next: (res) => this.detailCollaborators = res,
      error: () => {}
    });
  }

  private loadUserDirectory() {
    this.collaborationService.getUserDirectory().subscribe({
      next: (res) => this.userDirectory = res,
      error: () => {}
    });
  }

  get availableCollaboratorCandidates(): { id: number; email: string }[] {
    const collaboratorIds = new Set(this.detailCollaborators.map(c => c.user_id));
    return this.userDirectory.filter(u => u.id !== this.currentUserId && !collaboratorIds.has(u.id));
  }

  selectMyReviewRating(rating: number) {
    this.myReviewRating = rating;
  }

  submitMyReview() {
    if (!this.detailJob || this.myReviewRating === 0) return;
    this.detailError = '';
    this.collaborationService.upsertReview(this.detailJob.id, this.myReviewRating, this.myReviewComment).subscribe({
      next: () => this.loadDetailReviews(),
      error: (err) => { this.detailError = err.error?.detail || 'Could not submit your review.'; }
    });
  }

  deleteMyReview() {
    if (!this.detailJob) return;
    this.collaborationService.deleteOwnReview(this.detailJob.id).subscribe({
      next: () => {
        this.myReviewRating = 0;
        this.myReviewComment = '';
        this.loadDetailReviews();
      },
      error: (err) => { this.detailError = err.error?.detail || 'Could not delete your review.'; }
    });
  }

  addCollaborator() {
    if (!this.detailJob || !this.selectedCollaboratorUserId) return;
    this.collaboratorError = '';
    this.collaborationService.addCollaborator(this.detailJob.id, this.selectedCollaboratorUserId).subscribe({
      next: () => {
        this.selectedCollaboratorUserId = null;
        this.loadDetailCollaborators();
      },
      error: (err) => { this.collaboratorError = err.error?.detail || 'Could not add collaborator.'; }
    });
  }

  removeCollaborator(userId: number) {
    if (!this.detailJob) return;
    this.collaborationService.removeCollaborator(this.detailJob.id, userId).subscribe({
      next: () => this.loadDetailCollaborators(),
      error: (err) => { this.collaboratorError = err.error?.detail || 'Could not remove collaborator.'; }
    });
  }
}
