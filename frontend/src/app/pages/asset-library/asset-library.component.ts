import { Component, inject, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, Subscription, debounceTime, distinctUntilChanged } from 'rxjs';
import { BrandService, PortfolioItem } from '../../services/brand.service';
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
  baseUrl = environment.baseUrl;

  brands: any[] = [];
  selectedBrandId: number | null = null;
  activeTab: 'images' | 'blueprints' | 'knowledge' | 'portfolios' = 'images';

  images: any[] = [];
  blueprints: any[] = [];
  knowledge: any[] = [];
  portfolios: PortfolioItem[] = [];

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

  setTab(tab: 'images' | 'blueprints' | 'knowledge' | 'portfolios') {
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
}
