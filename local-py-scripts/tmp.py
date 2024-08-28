import xml.etree.ElementTree as ET
from shapely.geometry import Polygon, LinearRing
from shapely.validation import explain_validity
from shapely.ops import unary_union

def create_polygons_from_paths(paths, tolerance=1e-9, simplify_tolerance=1e-6):
    unique_polygons = []
    print(f"Number of paths: {len(paths)}")
    count = 0
    for path in paths:
        print(f"Processing path {count}")
        try:
            if len(path) > 1:
                print(f"Path has multiple rings: {path}\n")
                # First ring is the exterior, the rest are holes
                exterior = LinearRing(path[0])
                holes = [LinearRing(hole) for hole in path[1:] if len(hole) > 3]  # Ensure holes are valid rings
                polygon = Polygon(shell=exterior, holes=holes)
                print(f"Processed exterior and holes for path {count}\n")
            else:
                print(f"Path has a single ring: {path}\n")
                # Only one ring, no holes
                exterior = LinearRing(path[0])
                polygon = Polygon(shell=exterior)
                print(f"Processed single ring for path {count}\n")

            # Validate and fix the polygon if necessary
            if not polygon.is_valid:
                print(f"Invalid polygon detected: {explain_validity(polygon)}")
                polygon = polygon.buffer(0)  # Attempt to fix the polygon
                if not polygon.is_valid:
                    print(f"Polygon could not be fixed with buffer(0): {explain_validity(polygon)}")
                    polygon = unary_union([polygon])  # Attempt to fix with unary_union
                    if not polygon.is_valid:
                        print(f"Polygon could not be fixed with unary_union: {explain_validity(polygon)}")
                        continue  # Skip this polygon if it cannot be fixed

            # Simplify the polygon slightly to remove small variations
            simplified_polygon = polygon.simplify(simplify_tolerance, preserve_topology=True)

            # Normalize the polygon by buffering with a small distance and then reversing the buffer
            normalized_polygon = simplified_polygon.buffer(tolerance).buffer(-tolerance)

            print("Checking for duplicates...\n")
            # Check if this normalized polygon is equal to any existing one
            is_duplicate = any(existing_polygon.equals(normalized_polygon) for existing_polygon in unique_polygons)

            if not is_duplicate:
                print("Adding to unique polygons")
                unique_polygons.append(normalized_polygon)
            print(f"Finished processing path {count}\n")
            count += 1
        except Exception as e:
            print(f"Exception occurred: {e}")
            continue

    return unique_polygons

# Example path with issue
path_with_issue = [[(10.560375802266417, 59.95642756647558), (10.560549099414125, 59.9563926267068), (10.560680735210314, 59.95636283034607), (10.560823924125783, 59.956353607663), (10.560831276102633, 59.95626670158818), (10.560762307370121, 59.956183342744566), (10.560714694422563, 59.9561374066771), (10.560639073858795, 59.95605316104839), (10.560551199940528, 59.95595401719391), (10.560391906690551, 59.955805567434105), (10.560351645719841, 59.95573089918436), (10.560306483371484, 59.95563884974688), (10.560303682609863, 59.955558328606514), (10.560355146627057, 59.95548880376482), (10.560231212970137, 59.955461490456855), (10.560072969938549, 59.955439143163616), (10.56001625447091, 59.955333969115976), (10.559888469744356, 59.955297965168754), (10.559745280828887, 59.955324923780836), (10.55963815165207, 59.9553602182909), (10.559421092626438, 59.955343369146995), (10.55936052617879, 59.955252561190505), (10.559425643931291, 59.95518073068939), (10.559540124995333, 59.95514756449081), (10.55967666216917, 59.95507520190048), (10.559634650744854, 59.955007805370265), (10.559493912428586, 59.95491611062867), (10.55939133455662, 59.954869642471984), (10.559283155161415, 59.95490635585637), (10.55923799290268, 59.95497375238658), (10.559111258394518, 59.95499698646493), (10.558944963150863, 59.9549698504595), (10.558699196363428, 59.95505196782213), (10.558654734250288, 59.955138341807725), (10.558493340384281, 59.955197225092014), (10.55852449883491, 59.95527189334177), (10.55856020859039, 59.95533255024166), (10.558592417259407, 59.95538717690299), (10.558702697270641, 59.95537050510702), (10.558846236348533, 59.95535099560782), (10.559011131211378, 59.95540402600149), (10.559085701467131, 59.955520196347805), (10.559081150251902, 59.95557943437338), (10.55905209232768, 59.955688865043975), (10.559108457632895, 59.9557825107491), (10.559215586809714, 59.955827737379416), (10.559379081202122, 59.955860903532596), (10.559451200858677, 59.955892473508925), (10.559491111666965, 59.955982572028255), (10.559448400097056, 59.956034006199665), (10.559272302187727, 59.95606380256039), (10.55918197767026, 59.95612694251304), (10.559275102949348, 59.95618281065535), (10.559455402001108, 59.956245063777494), (10.559611194343873, 59.9562681204625), (10.559825102535086, 59.956305543284046), (10.560019405394952, 59.95638340402372), (10.560169596214473, 59.95644884959039), (10.560375802266417, 59.95642756647558), (10.560375802266417, 59.95642756647558)]]

# Test the function with the problematic path
create_polygons_from_paths([path_with_issue])