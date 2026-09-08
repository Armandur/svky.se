from fastapi import APIRouter

from . import account, bundles, domain_requests, links, swishsamlingar

router = APIRouter()
router.include_router(domain_requests.router)
router.include_router(links.router)
router.include_router(bundles.router)
router.include_router(swishsamlingar.router)
router.include_router(account.router)
