# -*- coding: UTF-8 -*-
"""
Views Module for Revit MCP
Handles view export and image generation functionality.

Only the ``/get_view/`` route remains here because it returns binary
image data.  View listing, properties, and element queries have been
migrated to internal stems.
"""

from pyrevit import routes, revit, DB
import tempfile
import os
import base64
import logging
from System.Collections.Generic import List

from utils import normalize_string, get_element_name

logger = logging.getLogger(__name__)


def register_views_routes(api):
    """Register all view-related routes with the API"""

    @api.route("/get_view/<view_name>", methods=["GET"])
    def get_view(doc, view_name):
        """
        Export a named Revit view as a PNG image and return the image data

        Args:
            doc: Revit document (provided by MCP context)
            view_name: Name of the view to export

        Returns:
            dict: Contains base64 encoded image data and content type, or error message
        """
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document"}, status=503
                )

            # Normalize the view name
            view_name = normalize_string(view_name)
            logger.info("Exporting view: {}".format(view_name))

            # Define output folder in temp directory
            output_folder = os.path.join(tempfile.gettempdir(), "RevitMCPExports")

            # Create output folder if it doesn't exist
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)

            # Create filename prefix
            file_path_prefix = os.path.join(output_folder, "export")

            # Find the view by name
            target_view = None
            all_views = DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()

            for view in all_views:
                try:
                    # Use safe name access
                    current_view_name = normalize_string(get_element_name(view))
                    if current_view_name == view_name:
                        target_view = view
                        break
                except Exception as e:
                    logger.warning("Could not get name for view: {}".format(str(e)))
                    continue

            if not target_view:
                # Get list of available views for better error message
                available_views = []
                for view in all_views:
                    try:
                        view_name_safe = normalize_string(get_element_name(view))
                        # Filter out system views and templates
                        if (
                            hasattr(view, "IsTemplate")
                            and not view.IsTemplate
                            and view.ViewType != DB.ViewType.Internal
                            and view.ViewType != DB.ViewType.ProjectBrowser
                        ):
                            available_views.append(view_name_safe)
                    except:
                        continue

                return routes.make_response(
                    data={
                        "error": "View '{}' not found".format(view_name),
                        "available_views": available_views[
                            :20
                        ],  # Limit to first 20 for readability
                    },
                    status=404,
                )

            # Check if view can be exported
            try:
                if hasattr(target_view, "IsTemplate") and target_view.IsTemplate:
                    return routes.make_response(
                        data={"error": "Cannot export view templates"}, status=400
                    )

                if target_view.ViewType == DB.ViewType.Internal:
                    return routes.make_response(
                        data={"error": "Cannot export internal views"}, status=400
                    )
            except Exception as e:
                logger.warning("Could not check view properties: {}".format(str(e)))

            # Set up export options
            ieo = DB.ImageExportOptions()
            ieo.ExportRange = DB.ExportRange.SetOfViews

            # Create list of view IDs to export
            viewIds = List[DB.ElementId]()
            viewIds.Add(target_view.Id)
            ieo.SetViewsAndSheets(viewIds)

            ieo.FilePath = file_path_prefix
            ieo.HLRandWFViewsFileType = DB.ImageFileType.PNG
            ieo.ShadowViewsFileType = DB.ImageFileType.PNG
            ieo.ImageResolution = DB.ImageResolution.DPI_150
            ieo.ZoomType = DB.ZoomFitType.FitToPage
            ieo.PixelSize = 1024  # Set a reasonable default size

            # Export the image
            logger.info("Starting image export for view: {}".format(view_name))
            doc.ExportImage(ieo)

            # Find the exported file (most recent PNG in folder)
            matching_files = []
            try:
                matching_files = [
                    os.path.join(output_folder, f)
                    for f in os.listdir(output_folder)
                    if f.endswith(".png")
                ]
                matching_files.sort(key=lambda x: os.path.getctime(x), reverse=True)
            except Exception as e:
                logger.error("Could not list exported files: {}".format(str(e)))
                return routes.make_response(
                    data={"error": "Could not access export folder"}, status=500
                )

            if not matching_files:
                return routes.make_response(
                    data={"error": "Export failed - no image file was created"},
                    status=500,
                )

            exported_file = matching_files[0]
            logger.info("Image exported successfully: {}".format(exported_file))

            # Read and encode the image
            try:
                with open(exported_file, "rb") as img_file:
                    img_data = img_file.read()

                encoded_data = base64.b64encode(img_data).decode("utf-8")

                # Get file size for logging
                file_size = len(img_data)
                logger.info(
                    "Image encoded successfully. Size: {} bytes".format(file_size)
                )

            except Exception as e:
                logger.error("Could not read/encode image file: {}".format(str(e)))
                return routes.make_response(
                    data={"error": "Could not read exported image file"}, status=500
                )
            finally:
                # Clean up the file
                try:
                    if os.path.exists(exported_file):
                        os.remove(exported_file)
                        logger.info("Temporary export file cleaned up")
                except Exception as e:
                    logger.warning(
                        "Could not clean up temporary file: {}".format(str(e))
                    )

            return routes.make_response(
                data={
                    "image_data": encoded_data,
                    "content_type": "image/png",
                    "view_name": view_name,
                    "file_size_bytes": len(img_data),
                    "export_success": True,
                }
            )

        except Exception as e:
            logger.error("Failed to export view '{}': {}".format(view_name, str(e)))
            return routes.make_response(
                data={"error": "Failed to export view: {}".format(str(e))}, status=500
            )

    logger.info("Views routes registered successfully (get_view only)")
