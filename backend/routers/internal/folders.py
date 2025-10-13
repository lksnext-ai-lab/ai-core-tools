from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

# Import services and schemas
from services.folder_service import FolderService
from schemas.folder_schemas import (
    FolderListItemSchema, FolderDetailSchema, FolderTreeSchema,
    CreateFolderSchema, UpdateFolderSchema, MoveFolderSchema,
    FoldersResponseSchema, FolderResponseSchema, FolderTreeResponseSchema
)
from schemas.common_schemas import MessageResponseSchema

# Import auth and database
from .auth_utils import get_current_user_oauth
from db.database import get_db
from fastapi import Request

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

folders_router = APIRouter()


@folders_router.get("/",
                   summary="Get root folders",
                   tags=["Folders"],
                   response_model=FoldersResponseSchema)
async def get_root_folders(
    app_id: int,
    repository_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get all root folders (parent_folder_id is None) for a repository.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Get root folders - app_id: {app_id}, repository_id: {repository_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    try:
        root_folders = FolderService.get_root_folders(repository_id, db)
        
        # Convert to schema format
        folder_items = []
        for folder in root_folders:
            # Get subfolder and resource counts
            from repositories.folder_repository import FolderRepository
            subfolder_count = len(FolderRepository.get_subfolders(db, folder.folder_id))
            resource_count = len(folder.resources)
            
            folder_item = FolderListItemSchema(
                folder_id=folder.folder_id,
                name=folder.name,
                parent_folder_id=folder.parent_folder_id,
                create_date=folder.create_date,
                status=folder.status,
                subfolder_count=subfolder_count,
                resource_count=resource_count
            )
            folder_items.append(folder_item)
        
        return FoldersResponseSchema(
            folders=folder_items,
            total_count=len(folder_items)
        )
    except Exception as e:
        logger.error(f"Error getting root folders: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get root folders"
        )


@folders_router.get("/tree",
                   summary="Get folder tree",
                   tags=["Folders"],
                   response_model=FolderTreeResponseSchema)
async def get_folder_tree(
    app_id: int,
    repository_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get the complete folder tree structure for a repository.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Get folder tree - app_id: {app_id}, repository_id: {repository_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    try:
        # Get all folders for the repository
        all_folders = FolderService.get_all_folders_in_repository(repository_id, db)
        
        # Get resources to count them per folder
        from services.resource_service import ResourceService
        all_resources = ResourceService.get_resources_by_repo_id(repository_id, db)
        resource_counts = {}
        for res in all_resources:
            folder_id = res.folder_id if res.folder_id else 0  # Use 0 for root
            resource_counts[folder_id] = resource_counts.get(folder_id, 0) + 1

        def build_tree(parent_id: Optional[int] = None) -> List[FolderTreeSchema]:
            tree = []
            for folder in all_folders:
                if folder.parent_folder_id == parent_id:
                    item = FolderTreeSchema(
                        folder_id=folder.folder_id,
                        name=folder.name,
                        create_date=folder.create_date,
                        status=folder.status,
                        repository_id=folder.repository_id,
                        parent_folder_id=folder.parent_folder_id,
                        resource_count=resource_counts.get(folder.folder_id, 0),
                        subfolders=build_tree(folder.folder_id)
                    )
                    tree.append(item)
            return tree

        # Root folders are those with parent_folder_id == None
        folder_tree = build_tree(None)
        return FolderTreeResponseSchema(folders=folder_tree)
    except Exception as e:
        logger.error(f"Error getting folder tree: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get folder tree"
        )


@folders_router.get("/{folder_id}",
                   summary="Get folder details",
                   tags=["Folders"],
                   response_model=FolderResponseSchema)
async def get_folder_details(
    app_id: int,
    repository_id: int,
    folder_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific folder.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Get folder details - app_id: {app_id}, repository_id: {repository_id}, folder_id: {folder_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    try:
        folder_data = FolderService.get_folder_with_contents(folder_id, db)
        if not folder_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found"
            )
        
        # Validate folder belongs to repository
        if not FolderService.validate_folder_access(folder_id, repository_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Folder does not belong to this repository"
            )
        
        # Add folder path
        folder_path = FolderService.get_folder_path(folder_id, db)
        folder_data['folder_path'] = folder_path
        
        folder_detail = FolderDetailSchema(**folder_data)
        return FolderResponseSchema(folder=folder_detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting folder details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get folder details"
        )


@folders_router.post("/",
                    summary="Create folder",
                    tags=["Folders"],
                    response_model=FolderResponseSchema,
                    status_code=201)
async def create_folder(
    app_id: int,
    repository_id: int,
    request: Request,
    folder_data: CreateFolderSchema,
    db: Session = Depends(get_db)
):
    """
    Create a new folder in the repository.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Create folder - app_id: {app_id}, repository_id: {repository_id}, name: {folder_data.name}, parent: {folder_data.parent_folder_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    try:
        created_folder = FolderService.create_folder(
            repository_id=repository_id,
            name=folder_data.name,
            parent_folder_id=folder_data.parent_folder_id,
            db=db
        )
        
        # Convert to response format
        folder_detail = FolderDetailSchema(
            folder_id=created_folder.folder_id,
            name=created_folder.name,
            parent_folder_id=created_folder.parent_folder_id,
            create_date=created_folder.create_date,
            status=created_folder.status,
            repository_id=created_folder.repository_id,
            subfolders=[],
            resources=[],
            folder_path=FolderService.get_folder_path(created_folder.folder_id, db)
        )
        
        return FolderResponseSchema(folder=folder_detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating folder: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create folder"
        )


@folders_router.put("/{folder_id}",
                   summary="Update folder",
                   tags=["Folders"],
                   response_model=FolderResponseSchema)
async def update_folder(
    app_id: int,
    repository_id: int,
    folder_id: int,
    request: Request,
    folder_data: UpdateFolderSchema,
    db: Session = Depends(get_db)
):
    """
    Update a folder's name.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Update folder - app_id: {app_id}, repository_id: {repository_id}, folder_id: {folder_id}, name: {folder_data.name}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    try:
        # Validate folder belongs to repository
        if not FolderService.validate_folder_access(folder_id, repository_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Folder does not belong to this repository"
            )
        
        updated_folder = FolderService.update_folder(
            folder_id=folder_id,
            name=folder_data.name,
            db=db
        )
        
        # Convert to response format
        folder_detail = FolderDetailSchema(
            folder_id=updated_folder.folder_id,
            name=updated_folder.name,
            parent_folder_id=updated_folder.parent_folder_id,
            create_date=updated_folder.create_date,
            status=updated_folder.status,
            repository_id=updated_folder.repository_id,
            subfolders=[],
            resources=[],
            folder_path=FolderService.get_folder_path(updated_folder.folder_id, db)
        )
        
        return FolderResponseSchema(folder=folder_detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating folder: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update folder"
        )


@folders_router.delete("/{folder_id}",
                      summary="Delete folder",
                      tags=["Folders"],
                      response_model=MessageResponseSchema)
async def delete_folder(
    app_id: int,
    repository_id: int,
    folder_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Delete a folder and all its contents (subfolders and resources).
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Delete folder - app_id: {app_id}, repository_id: {repository_id}, folder_id: {folder_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    try:
        # Validate folder belongs to repository
        if not FolderService.validate_folder_access(folder_id, repository_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Folder does not belong to this repository"
            )
        
        FolderService.delete_folder(folder_id, db)
        
        return MessageResponseSchema(
            message=f"Folder {folder_id} and all its contents have been deleted successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting folder: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete folder"
        )


@folders_router.post("/{folder_id}/move",
                    summary="Move folder",
                    tags=["Folders"],
                    response_model=FolderResponseSchema)
async def move_folder(
    app_id: int,
    repository_id: int,
    folder_id: int,
    request: Request,
    move_data: MoveFolderSchema,
    db: Session = Depends(get_db)
):
    """
    Move a folder to a new parent folder.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Move folder - app_id: {app_id}, repository_id: {repository_id}, folder_id: {folder_id}, new_parent: {move_data.new_parent_folder_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    try:
        # Validate folder belongs to repository
        if not FolderService.validate_folder_access(folder_id, repository_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Folder does not belong to this repository"
            )
        
        moved_folder = FolderService.move_folder(
            folder_id=folder_id,
            new_parent_folder_id=move_data.new_parent_folder_id,
            db=db
        )
        
        # Convert to response format
        folder_detail = FolderDetailSchema(
            folder_id=moved_folder.folder_id,
            name=moved_folder.name,
            parent_folder_id=moved_folder.parent_folder_id,
            create_date=moved_folder.create_date,
            status=moved_folder.status,
            repository_id=moved_folder.repository_id,
            subfolders=[],
            resources=[],
            folder_path=FolderService.get_folder_path(moved_folder.folder_id, db)
        )
        
        return FolderResponseSchema(folder=folder_detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moving folder: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to move folder"
        )


def _convert_folder_data_to_tree_schema(folder_data: dict) -> FolderTreeSchema:
    """
    Convert folder data dictionary to FolderTreeSchema
    """
    subfolders = []
    for subfolder_data in folder_data.get('subfolders', []):
        subfolder = _convert_folder_data_to_tree_schema(subfolder_data)
        subfolders.append(subfolder)
    
    return FolderTreeSchema(
        folder_id=folder_data['folder_id'],
        name=folder_data['name'],
        parent_folder_id=folder_data.get('parent_folder_id'),
        create_date=folder_data.get('create_date'),
        status=folder_data.get('status'),
        repository_id=folder_data['repository_id'],
        subfolders=subfolders,
        resource_count=folder_data.get('resource_count', 0),
        folder_path=folder_data.get('folder_path', '')
    )
